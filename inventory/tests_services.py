from decimal import Decimal

from core.factories import (
    BaseFixtureTestCase,
    approve_initial_count,
    create_item,
    create_managed_item,
    create_supplier,
)
from inventory.exceptions import (
    DuplicateInitialCountError,
    InitialCountRequiredError,
    InsufficientStockError,
    InvalidQuantityError,
    InvalidTransactionStateError,
    InventoryError,
    PermissionDeniedError,
)
from inventory.models import ItemCategory, TransactionStatus, TransactionType
from inventory.selectors import get_current_stock
from inventory.services import (
    create_stock_in,
    create_stock_out,
    request_adjustment,
    request_initial_count,
)


class StockInServiceTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.supplier = create_supplier(name="메디칼코리아")
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi_skin = create_managed_item(
            item=cls.item, department=cls.dept_skin, default_supplier=cls.supplier
        )
        cls.mi_treatment = create_managed_item(
            item=cls.item, department=cls.dept_treatment
        )
        # 입고 전제: 승인된 최초재고가 있어야 한다 (HOTFIX) — 수량 0 으로 시드
        approve_initial_count(cls.mi_skin, created_by=cls.manager)

    def test_create_stock_in_success(self):
        """7.1 create_stock_in 성공 테스트"""
        tx = create_stock_in(
            user=self.staff_skin, managed_item=self.mi_skin, quantity=10
        )
        self.assertEqual(tx.transaction_type, TransactionType.IN)
        self.assertEqual(tx.status, TransactionStatus.APPROVED)
        self.assertEqual(tx.quantity_delta, Decimal("10"))
        self.assertEqual(tx.created_by, self.staff_skin)  # created_by 기록
        self.assertEqual(get_current_stock(self.mi_skin), Decimal("10"))

    def test_create_stock_in_other_department_blocked(self):
        """7.2 create_stock_in 타 부서 차단 테스트"""
        with self.assertRaises(PermissionDeniedError):
            create_stock_in(
                user=self.staff_skin, managed_item=self.mi_treatment, quantity=5
            )

    def test_create_stock_in_quantity_zero_blocked(self):
        """7.3 create_stock_in quantity 0 차단 테스트"""
        with self.assertRaises(InvalidQuantityError):
            create_stock_in(
                user=self.staff_skin, managed_item=self.mi_skin, quantity=0
            )

    def test_create_stock_in_negative_blocked(self):
        """7.4 create_stock_in 음수 차단 테스트"""
        with self.assertRaises(InvalidQuantityError):
            create_stock_in(
                user=self.staff_skin, managed_item=self.mi_skin, quantity=-3
            )

    def test_create_stock_in_supplier_default(self):
        """7.6 supplier 기본값 테스트"""
        tx = create_stock_in(
            user=self.staff_skin, managed_item=self.mi_skin, quantity=5
        )
        self.assertEqual(tx.supplier, self.supplier)


class StockOutServiceTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi_skin = create_managed_item(item=cls.item, department=cls.dept_skin)
        cls.mi_treatment = create_managed_item(
            item=cls.item, department=cls.dept_treatment
        )
        # 출고 전제: 승인된 최초재고가 있어야 한다 (HOTFIX) — 수량 0 으로 시드
        approve_initial_count(cls.mi_skin, created_by=cls.manager)

    def _stock_in(self, qty):
        return create_stock_in(
            user=self.staff_skin, managed_item=self.mi_skin, quantity=qty
        )

    def test_create_stock_out_success(self):
        """8.1 create_stock_out 성공 테스트"""
        self._stock_in(10)
        tx = create_stock_out(
            user=self.staff_skin,
            managed_item=self.mi_skin,
            transaction_type=TransactionType.OUT_USE,
            quantity=3,
        )
        self.assertEqual(tx.quantity_delta, Decimal("-3"))
        self.assertEqual(get_current_stock(self.mi_skin), Decimal("7"))

    def test_out_exceeding_stock_blocked(self):
        """8.2 현재고 초과 출고 차단 테스트"""
        self._stock_in(10)
        with self.assertRaises(InsufficientStockError):
            create_stock_out(
                user=self.staff_skin,
                managed_item=self.mi_skin,
                transaction_type=TransactionType.OUT_USE,
                quantity=11,
            )

    def test_out_equal_to_stock_allowed(self):
        """8.3 현재고와 같은 수량 출고 허용 테스트"""
        self._stock_in(10)
        create_stock_out(
            user=self.staff_skin,
            managed_item=self.mi_skin,
            transaction_type=TransactionType.OUT_USE,
            quantity=10,
        )
        self.assertEqual(get_current_stock(self.mi_skin), Decimal("0"))

    def test_non_out_type_blocked(self):
        """8.4 OUT 계열 외 transaction_type 차단 테스트"""
        self._stock_in(10)
        with self.assertRaises(InvalidTransactionStateError):
            create_stock_out(
                user=self.staff_skin,
                managed_item=self.mi_skin,
                transaction_type=TransactionType.IN,
                quantity=1,
            )

    def test_out_other_department_blocked(self):
        """8.5 타 부서 출고 차단 테스트"""
        with self.assertRaises(PermissionDeniedError):
            create_stock_out(
                user=self.staff_skin,
                managed_item=self.mi_treatment,
                transaction_type=TransactionType.OUT_USE,
                quantity=1,
            )


class AdjustmentServiceTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)
        # 입고/출고 전제: 승인된 최초재고가 있어야 한다 (HOTFIX) — 수량 0 으로 시드
        approve_initial_count(cls.mi, created_by=cls.manager)

    def _set_stock_7(self):
        create_stock_in(user=self.staff_skin, managed_item=self.mi, quantity=10)
        create_stock_out(
            user=self.staff_skin,
            managed_item=self.mi,
            transaction_type=TransactionType.OUT_USE,
            quantity=3,
        )

    def test_request_adjustment_success_and_delta(self):
        """9.1 request_adjustment 성공 + 실사조정 delta 정합성 테스트"""
        self._set_stock_7()
        tx = request_adjustment(
            user=self.team_leader_skin,
            managed_item=self.mi,
            actual_quantity=5,
            reason="실사 결과 차이",
        )
        self.assertEqual(tx.status, TransactionStatus.PENDING)
        self.assertEqual(tx.expected_quantity, Decimal("7"))
        self.assertEqual(tx.actual_quantity, Decimal("5"))
        self.assertEqual(tx.quantity_delta, Decimal("-2"))
        # PENDING 이므로 현재고는 아직 7 유지
        self.assertEqual(get_current_stock(self.mi), Decimal("7"))

    def test_adjustment_reason_required(self):
        """9.2 adjustment reason 필수 테스트"""
        with self.assertRaises(InventoryError):
            request_adjustment(
                user=self.team_leader_skin,
                managed_item=self.mi,
                actual_quantity=5,
                reason="   ",
            )

    def test_adjustment_actual_negative_blocked(self):
        """9.3 actual_quantity 음수 차단 테스트"""
        with self.assertRaises(InvalidQuantityError):
            request_adjustment(
                user=self.team_leader_skin,
                managed_item=self.mi,
                actual_quantity=-1,
                reason="음수 테스트",
            )

    def test_staff_adjustment_blocked(self):
        """실사조정 요청은 STAFF 불가 (TEAM_LEADER 이상)"""
        from inventory.exceptions import PermissionDeniedError

        with self.assertRaises(PermissionDeniedError):
            request_adjustment(
                user=self.staff_skin, managed_item=self.mi,
                actual_quantity=5, reason="실물 재고 부족",
            )


class InitialCountServiceTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)

    def test_staff_initial_count_blocked(self):
        """A-3: STAFF 는 초기재고 입력 불가"""
        from inventory.exceptions import PermissionDeniedError

        with self.assertRaises(PermissionDeniedError):
            request_initial_count(
                user=self.staff_skin, managed_item=self.mi, quantity=20
            )

    def test_team_leader_initial_count_pending(self):
        """A-3: TEAM_LEADER 초기재고 요청 (PENDING)"""
        tx = request_initial_count(
            user=self.team_leader_skin, managed_item=self.mi, quantity=20
        )
        self.assertEqual(tx.status, TransactionStatus.PENDING)
        self.assertEqual(tx.quantity_delta, Decimal("20"))
        # PENDING 이므로 현재고 미반영
        self.assertEqual(get_current_stock(self.mi), Decimal("0"))

    def test_manager_initial_count_approved(self):
        """10.2 MANAGER 초기재고 즉시 승인 테스트

        정책: 즉시 APPROVED 시 created_by / approved_by 를 모두 해당 user 로,
        approved_at 도 함께 기록한다. (감사 추적성 유지)
        """
        tx = request_initial_count(
            user=self.manager, managed_item=self.mi, quantity=20
        )
        self.assertEqual(tx.status, TransactionStatus.APPROVED)
        self.assertEqual(tx.created_by, self.manager)
        self.assertEqual(tx.approved_by, self.manager)
        self.assertIsNotNone(tx.approved_at)
        self.assertEqual(get_current_stock(self.mi), Decimal("20"))

    def test_duplicate_approved_initial_count_blocked(self):
        """10.3 이미 승인된 초기재고가 있으면 요청 차단"""
        request_initial_count(user=self.manager, managed_item=self.mi, quantity=20)
        with self.assertRaises(DuplicateInitialCountError):
            request_initial_count(
                user=self.manager, managed_item=self.mi, quantity=5
            )

    def test_pending_initial_count_duplicate_blocked(self):
        """10.4 PENDING 초기재고가 있으면 중복 최초재고 요청 차단 (HOTFIX)"""
        request_initial_count(user=self.team_leader_skin, managed_item=self.mi, quantity=20)
        # 승인대기(PENDING) 최초재고가 이미 있으므로 두 번째 요청은 차단된다.
        with self.assertRaises(DuplicateInitialCountError):
            request_initial_count(
                user=self.team_leader_skin, managed_item=self.mi, quantity=18
            )
        pending = self.mi.stock_transactions.filter(
            transaction_type=TransactionType.INITIAL_COUNT,
            status=TransactionStatus.PENDING,
        )
        self.assertEqual(pending.count(), 1)


class InitialCountGuardTest(BaseFixtureTestCase):
    """HOTFIX: 승인된 최초재고가 없으면 입고/출고를 차단한다.

    - 승인된 INITIAL_COUNT 가 없으면 입고/출고 실패
    - PENDING(승인대기) INITIAL_COUNT 만 있어도 입고/출고 실패
    - 승인된 INITIAL_COUNT(수량 0 포함)가 있으면 입고/출고 가능
    - 최초재고가 없는 품목에서 INITIAL_COUNT 요청 자체는 가능
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)

    def _approve_initial(self, quantity):
        """MANAGER 의 최초 재고 입력(즉시 APPROVED)."""
        return request_initial_count(
            user=self.manager, managed_item=self.mi, quantity=quantity
        )

    # --- 1: 승인된 최초재고 없음 → 입고 실패 ---
    def test_stock_in_blocked_without_initial_count(self):
        with self.assertRaises(InitialCountRequiredError) as ctx:
            create_stock_in(user=self.staff_skin, managed_item=self.mi, quantity=10)
        self.assertIn("최초 재고 등록이 승인되지 않아", str(ctx.exception))

    # --- 2: 승인된 최초재고 없음 → 출고 실패 ---
    def test_stock_out_blocked_without_initial_count(self):
        with self.assertRaises(InitialCountRequiredError) as ctx:
            create_stock_out(
                user=self.staff_skin,
                managed_item=self.mi,
                transaction_type=TransactionType.OUT_USE,
                quantity=1,
            )
        self.assertIn("최초 재고 등록이 승인되지 않아", str(ctx.exception))

    # --- 3: PENDING 최초재고만 있음 → 입고/출고 실패 (승인대기 안내) ---
    def test_stock_in_blocked_with_pending_initial_count(self):
        request_initial_count(
            user=self.team_leader_skin, managed_item=self.mi, quantity=20
        )  # PENDING
        with self.assertRaises(InitialCountRequiredError) as ctx:
            create_stock_in(user=self.staff_skin, managed_item=self.mi, quantity=10)
        self.assertIn("승인 대기 중", str(ctx.exception))

    def test_stock_out_blocked_with_pending_initial_count(self):
        request_initial_count(
            user=self.team_leader_skin, managed_item=self.mi, quantity=20
        )  # PENDING
        with self.assertRaises(InitialCountRequiredError) as ctx:
            create_stock_out(
                user=self.staff_skin,
                managed_item=self.mi,
                transaction_type=TransactionType.OUT_USE,
                quantity=1,
            )
        self.assertIn("승인 대기 중", str(ctx.exception))

    # --- 4 & 5: 승인된 최초재고 있음 → 입고/출고 가능 ---
    def test_stock_in_allowed_with_approved_initial_count(self):
        self._approve_initial(20)
        tx = create_stock_in(user=self.staff_skin, managed_item=self.mi, quantity=10)
        self.assertEqual(tx.status, TransactionStatus.APPROVED)
        self.assertEqual(get_current_stock(self.mi), Decimal("30"))

    def test_stock_out_allowed_with_approved_initial_count(self):
        self._approve_initial(20)
        tx = create_stock_out(
            user=self.staff_skin,
            managed_item=self.mi,
            transaction_type=TransactionType.OUT_USE,
            quantity=5,
        )
        self.assertEqual(tx.status, TransactionStatus.APPROVED)
        self.assertEqual(get_current_stock(self.mi), Decimal("15"))

    # --- 6: 최초재고 0 으로 승인된 품목도 입고/출고 가능 ---
    def test_stock_in_out_allowed_with_zero_initial_count(self):
        self._approve_initial(0)
        create_stock_in(user=self.staff_skin, managed_item=self.mi, quantity=10)
        create_stock_out(
            user=self.staff_skin,
            managed_item=self.mi,
            transaction_type=TransactionType.OUT_USE,
            quantity=4,
        )
        self.assertEqual(get_current_stock(self.mi), Decimal("6"))

    # --- 5(요청 보장): 최초재고가 없으면 INITIAL_COUNT 요청 자체는 가능 ---
    def test_initial_count_request_allowed_when_none_exists(self):
        tx = request_initial_count(
            user=self.team_leader_skin, managed_item=self.mi, quantity=15
        )
        self.assertEqual(tx.transaction_type, TransactionType.INITIAL_COUNT)
        self.assertEqual(tx.status, TransactionStatus.PENDING)
