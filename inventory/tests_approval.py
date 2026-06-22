from decimal import Decimal

from core.factories import BaseFixtureTestCase, create_item, create_managed_item
from inventory.exceptions import (
    DuplicateInitialCountError,
    InsufficientStockError,
    InvalidTransactionStateError,
    InventoryError,
    PermissionDeniedError,
)
from inventory.models import ItemCategory, TransactionStatus, TransactionType
from inventory.selectors import get_current_stock
from inventory.services import (
    approve_transaction,
    create_stock_in,
    create_stock_out,
    reject_transaction,
    request_adjustment,
    request_initial_count,
    withdraw_pending_transaction,
)


class ApprovalServiceTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)

    # --- helper ---
    def _pending_adjustment(self, *, stock_in=10, actual=7, creator=None):
        # 실사조정은 TEAM_LEADER 이상만 (v0.1.1)
        creator = creator or self.team_leader_skin
        create_stock_in(user=self.manager, managed_item=self.mi, quantity=stock_in)
        return request_adjustment(
            user=creator,
            managed_item=self.mi,
            actual_quantity=actual,
            reason="실사 차이",
        )

    def _pending_initial(self, *, qty=20, creator=None):
        # 초기재고는 TEAM_LEADER 이상만 (A-3) → 기본 생성자 팀장
        creator = creator or self.team_leader_skin
        return request_initial_count(
            user=creator, managed_item=self.mi, quantity=qty
        )

    # ---------------- ADJUSTMENT ----------------
    def test_approve_adjustment_success(self):
        """9.4 adjustment 승인 성공 테스트 + approved_by/approved_at 기록"""
        tx = self._pending_adjustment(stock_in=10, actual=7)  # delta -3
        approved = approve_transaction(user=self.manager, transaction_obj=tx)
        self.assertEqual(approved.status, TransactionStatus.APPROVED)
        self.assertEqual(approved.approved_by, self.manager)
        self.assertIsNotNone(approved.approved_at)
        self.assertEqual(get_current_stock(self.mi), Decimal("7"))

    def test_approve_adjustment_negative_blocked(self):
        """9.5 adjustment 승인 시 현재고 음수 차단 테스트"""
        # 요청 시점 현재고 10 → actual 2 → delta -8 (PENDING)
        tx = self._pending_adjustment(stock_in=10, actual=2)
        # 이후 출고 5 → 현재고 5. 승인하면 5 + (-8) = -3 → 차단
        create_stock_out(
            user=self.staff_skin,
            managed_item=self.mi,
            transaction_type=TransactionType.OUT_USE,
            quantity=5,
        )
        with self.assertRaises(InsufficientStockError):
            approve_transaction(user=self.manager, transaction_obj=tx)

    def test_reject_adjustment(self):
        """9.6 adjustment 반려 테스트 + rejected approved_by/approved_at 기록"""
        tx = self._pending_adjustment(stock_in=10, actual=7)
        rejected = reject_transaction(
            user=self.manager, transaction_obj=tx, review_note="근거 불충분"
        )
        self.assertEqual(rejected.status, TransactionStatus.REJECTED)
        self.assertEqual(rejected.approved_by, self.manager)
        self.assertIsNotNone(rejected.approved_at)
        # 현재고 미반영 (10 유지)
        self.assertEqual(get_current_stock(self.mi), Decimal("10"))

    def test_withdraw_adjustment(self):
        """9.7 adjustment 철회 테스트 + canceled_by/canceled_at 기록"""
        tx = self._pending_adjustment(stock_in=10, actual=7, creator=self.team_leader_skin)
        canceled = withdraw_pending_transaction(
            user=self.team_leader_skin, transaction_obj=tx, cancel_reason="요청 취소"
        )
        self.assertEqual(canceled.status, TransactionStatus.CANCELED)
        self.assertEqual(canceled.canceled_by, self.team_leader_skin)
        self.assertIsNotNone(canceled.canceled_at)
        self.assertEqual(get_current_stock(self.mi), Decimal("10"))

    # ---------------- INITIAL_COUNT ----------------
    def test_approve_initial_count_success(self):
        """10.5 초기재고 승인 성공 테스트"""
        tx = self._pending_initial(qty=20)
        approved = approve_transaction(user=self.manager, transaction_obj=tx)
        self.assertEqual(approved.status, TransactionStatus.APPROVED)
        self.assertEqual(approved.approved_by, self.manager)
        self.assertIsNotNone(approved.approved_at)
        self.assertEqual(get_current_stock(self.mi), Decimal("20"))

    def test_approve_initial_count_duplicate_blocked(self):
        """10.6 초기재고 승인 시 중복 차단 테스트"""
        tx1 = self._pending_initial(qty=20)
        tx2 = self._pending_initial(qty=18)  # PENDING 중복 허용
        approve_transaction(user=self.manager, transaction_obj=tx1)
        with self.assertRaises(DuplicateInitialCountError):
            approve_transaction(user=self.manager, transaction_obj=tx2)

    def test_reject_initial_count(self):
        """10.7 초기재고 반려 테스트"""
        tx = self._pending_initial(qty=20)
        rejected = reject_transaction(
            user=self.manager, transaction_obj=tx, review_note="재실사 필요"
        )
        self.assertEqual(rejected.status, TransactionStatus.REJECTED)
        self.assertEqual(get_current_stock(self.mi), Decimal("0"))

    def test_withdraw_initial_count(self):
        """10.8 초기재고 철회 테스트"""
        tx = self._pending_initial(qty=20, creator=self.team_leader_skin)
        canceled = withdraw_pending_transaction(
            user=self.team_leader_skin, transaction_obj=tx, cancel_reason="중복 입력"
        )
        self.assertEqual(canceled.status, TransactionStatus.CANCELED)
        self.assertEqual(canceled.canceled_by, self.team_leader_skin)

    # ---------------- 권한 / 상태 전이 ----------------
    def test_approve_permission_denied_for_staff_and_leader(self):
        """11.1 APPROVE 권한 테스트 (STAFF/TEAM_LEADER 불가)"""
        tx = self._pending_initial(qty=20)
        with self.assertRaises(PermissionDeniedError):
            approve_transaction(user=self.staff_skin, transaction_obj=tx)
        with self.assertRaises(PermissionDeniedError):
            approve_transaction(user=self.team_leader_skin, transaction_obj=tx)

    def test_approve_allowed_for_manager(self):
        """11.2 MANAGER 승인 가능 테스트"""
        tx = self._pending_initial(qty=20)
        approved = approve_transaction(user=self.manager, transaction_obj=tx)
        self.assertEqual(approved.status, TransactionStatus.APPROVED)

    def test_reject_permission_denied_for_staff(self):
        """11.3 REJECT 권한 테스트"""
        tx = self._pending_initial(qty=20)
        with self.assertRaises(PermissionDeniedError):
            reject_transaction(
                user=self.staff_skin, transaction_obj=tx, review_note="x"
            )

    def test_reject_review_note_required(self):
        """11.4 REJECT review_note 필수 테스트"""
        tx = self._pending_initial(qty=20)
        with self.assertRaises(InventoryError):
            reject_transaction(
                user=self.manager, transaction_obj=tx, review_note="   "
            )

    def test_canceled_cannot_be_approved(self):
        """11.5 CANCELED 거래 재승인 차단 테스트"""
        tx = self._pending_initial(qty=20, creator=self.team_leader_skin)
        withdraw_pending_transaction(
            user=self.team_leader_skin, transaction_obj=tx, cancel_reason="취소"
        )
        with self.assertRaises(InvalidTransactionStateError):
            approve_transaction(user=self.manager, transaction_obj=tx)

    def test_rejected_cannot_be_approved(self):
        """11.6 REJECTED 거래 재승인 차단 테스트"""
        tx = self._pending_initial(qty=20)
        reject_transaction(
            user=self.manager, transaction_obj=tx, review_note="반려"
        )
        with self.assertRaises(InvalidTransactionStateError):
            approve_transaction(user=self.manager, transaction_obj=tx)

    def test_withdraw_by_creator_allowed(self):
        """11.7 PENDING 철회 생성자 가능 테스트"""
        tx = self._pending_initial(qty=20, creator=self.team_leader_skin)
        canceled = withdraw_pending_transaction(
            user=self.team_leader_skin, transaction_obj=tx, cancel_reason="생성자 철회"
        )
        self.assertEqual(canceled.status, TransactionStatus.CANCELED)

    def test_withdraw_by_other_denied(self):
        """11.8 PENDING 철회 타인 차단 테스트"""
        tx = self._pending_initial(qty=20, creator=self.team_leader_skin)
        # staff_skin 은 생성자도 MANAGER도 아님 → 차단
        with self.assertRaises(PermissionDeniedError):
            withdraw_pending_transaction(
                user=self.staff_skin,
                transaction_obj=tx,
                cancel_reason="타인 시도",
            )
