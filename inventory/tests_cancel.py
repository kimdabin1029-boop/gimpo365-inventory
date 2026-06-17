from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from core.factories import BaseFixtureTestCase, create_item, create_managed_item
from inventory.exceptions import (
    InsufficientStockError,
    InvalidTransactionStateError,
    PermissionDeniedError,
)
from inventory.models import (
    ItemCategory,
    StockTransaction,
    TransactionStatus,
    TransactionType,
)
from inventory.selectors import get_current_stock
from inventory.services import (
    approve_transaction,
    cancel_transaction,
    create_stock_in,
    create_stock_out,
    request_adjustment,
    request_initial_count,
)


class CancelTransactionTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi_skin = create_managed_item(item=cls.item, department=cls.dept_skin)
        cls.mi_treatment = create_managed_item(
            item=cls.item, department=cls.dept_treatment
        )

    def _in(self, *, user, mi, qty=10):
        return create_stock_in(user=user, managed_item=mi, quantity=qty)

    def _set_yesterday(self, tx):
        StockTransaction.objects.filter(pk=tx.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )
        tx.refresh_from_db()
        return tx

    def test_staff_own_today_cancel(self):
        """12.1 STAFF 당일 본인 거래 취소 가능"""
        tx = self._in(user=self.staff_skin, mi=self.mi_skin, qty=10)
        canceled = cancel_transaction(
            user=self.staff_skin, transaction_obj=tx, cancel_reason="오입력"
        )
        self.assertEqual(canceled.status, TransactionStatus.CANCELED)
        self.assertEqual(canceled.canceled_by, self.staff_skin)
        self.assertIsNotNone(canceled.canceled_at)
        self.assertEqual(get_current_stock(self.mi_skin), Decimal("0"))

    def test_staff_other_user_cancel_denied(self):
        """12.2 STAFF 타인 거래 취소 차단"""
        tx = self._in(user=self.team_leader_skin, mi=self.mi_skin, qty=10)
        with self.assertRaises(PermissionDeniedError):
            cancel_transaction(
                user=self.staff_skin, transaction_obj=tx, cancel_reason="x"
            )

    def test_staff_previous_day_cancel_denied(self):
        """12.3 STAFF 전일 거래 취소 차단"""
        tx = self._in(user=self.staff_skin, mi=self.mi_skin, qty=10)
        self._set_yesterday(tx)
        with self.assertRaises(PermissionDeniedError):
            cancel_transaction(
                user=self.staff_skin, transaction_obj=tx, cancel_reason="x"
            )

    def test_team_leader_own_department_today_cancel(self):
        """12.4 TEAM_LEADER 본인 부서 당일 거래 취소 가능"""
        tx = self._in(user=self.staff_skin, mi=self.mi_skin, qty=10)
        canceled = cancel_transaction(
            user=self.team_leader_skin, transaction_obj=tx, cancel_reason="팀장 정정"
        )
        self.assertEqual(canceled.status, TransactionStatus.CANCELED)

    def test_team_leader_other_department_cancel_denied(self):
        """12.5 TEAM_LEADER 타 부서 거래 취소 차단"""
        tx = self._in(user=self.staff_treatment, mi=self.mi_treatment, qty=10)
        with self.assertRaises(PermissionDeniedError):
            cancel_transaction(
                user=self.team_leader_skin, transaction_obj=tx, cancel_reason="x"
            )

    def test_manager_any_cancel(self):
        """12.6 MANAGER 전체 거래 취소 가능"""
        tx = self._in(user=self.staff_treatment, mi=self.mi_treatment, qty=10)
        canceled = cancel_transaction(
            user=self.manager, transaction_obj=tx, cancel_reason="운영 정정"
        )
        self.assertEqual(canceled.status, TransactionStatus.CANCELED)

    def test_cancel_negative_blocked(self):
        """12.7 취소 후 현재고 음수 차단 테스트"""
        in_tx = self._in(user=self.staff_skin, mi=self.mi_skin, qty=10)
        create_stock_out(
            user=self.staff_skin,
            managed_item=self.mi_skin,
            transaction_type=TransactionType.OUT_USE,
            quantity=8,
        )
        # 입고(+10) 취소 시 2 - 10 = -8 → 차단
        with self.assertRaises(InsufficientStockError):
            cancel_transaction(
                user=self.manager, transaction_obj=in_tx, cancel_reason="x"
            )

    def test_out_cancel_success(self):
        """12.8 OUT 거래 취소 성공 테스트"""
        self._in(user=self.staff_skin, mi=self.mi_skin, qty=10)
        out_tx = create_stock_out(
            user=self.staff_skin,
            managed_item=self.mi_skin,
            transaction_type=TransactionType.OUT_USE,
            quantity=3,
        )
        self.assertEqual(get_current_stock(self.mi_skin), Decimal("7"))
        cancel_transaction(
            user=self.staff_skin, transaction_obj=out_tx, cancel_reason="오입력"
        )
        self.assertEqual(get_current_stock(self.mi_skin), Decimal("10"))

    def test_initial_count_cancel_blocked(self):
        """12.9 INITIAL_COUNT 취소 차단 테스트"""
        tx = request_initial_count(
            user=self.manager, managed_item=self.mi_skin, quantity=20
        )  # 즉시 APPROVED
        with self.assertRaises(InvalidTransactionStateError):
            cancel_transaction(
                user=self.manager, transaction_obj=tx, cancel_reason="x"
            )

    def test_adjustment_cancel_blocked(self):
        """12.10 ADJUSTMENT 취소 차단 테스트"""
        self._in(user=self.manager, mi=self.mi_skin, qty=10)
        adj = request_adjustment(
            user=self.staff_skin,
            managed_item=self.mi_skin,
            actual_quantity=7,
            reason="실사",
        )
        approve_transaction(user=self.manager, transaction_obj=adj)  # APPROVED ADJUSTMENT
        with self.assertRaises(InvalidTransactionStateError):
            cancel_transaction(
                user=self.manager, transaction_obj=adj, cancel_reason="x"
            )
