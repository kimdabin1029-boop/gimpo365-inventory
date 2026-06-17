from decimal import Decimal

from core.factories import (
    BaseFixtureTestCase,
    create_item,
    create_managed_item,
    create_stock_transaction,
)
from inventory.models import ItemCategory, TransactionStatus, TransactionType
from inventory.selectors import (
    get_accessible_managed_items,
    get_current_stock,
    get_low_stock_managed_items,
    has_approved_initial_count,
)


class GetCurrentStockTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)

    def _tx(self, *, ttype, status, delta, qin=0):
        return create_stock_transaction(
            managed_item=self.mi,
            transaction_type=ttype,
            created_by=self.staff_skin,
            status=status,
            quantity_input=qin,
            quantity_delta=delta,
        )

    def test_basic_sum(self):
        """6.1 get_current_stock 기본 테스트"""
        self._tx(ttype=TransactionType.IN, status=TransactionStatus.APPROVED, delta=10, qin=10)
        self._tx(ttype=TransactionType.OUT_USE, status=TransactionStatus.APPROVED, delta=-3, qin=3)
        self.assertEqual(get_current_stock(self.mi), Decimal("7"))

    def test_pending_excluded(self):
        """6.2 PENDING 거래 제외 테스트"""
        self._tx(ttype=TransactionType.IN, status=TransactionStatus.APPROVED, delta=10, qin=10)
        self._tx(ttype=TransactionType.ADJUSTMENT, status=TransactionStatus.PENDING, delta=5)
        self.assertEqual(get_current_stock(self.mi), Decimal("10"))

    def test_rejected_excluded(self):
        """6.3 REJECTED 거래 제외 테스트"""
        self._tx(ttype=TransactionType.IN, status=TransactionStatus.APPROVED, delta=10, qin=10)
        self._tx(ttype=TransactionType.ADJUSTMENT, status=TransactionStatus.REJECTED, delta=5)
        self.assertEqual(get_current_stock(self.mi), Decimal("10"))

    def test_canceled_excluded(self):
        """6.4 CANCELED 거래 제외 테스트"""
        self._tx(ttype=TransactionType.IN, status=TransactionStatus.APPROVED, delta=10, qin=10)
        self._tx(ttype=TransactionType.IN, status=TransactionStatus.CANCELED, delta=5, qin=5)
        self.assertEqual(get_current_stock(self.mi), Decimal("10"))

    def test_no_transactions_returns_zero(self):
        """6.5 거래가 없으면 0 반환"""
        empty_item = create_item("니들 30G", category=ItemCategory.MEDICAL_SUPPLY)
        empty_mi = create_managed_item(item=empty_item, department=self.dept_skin)
        self.assertEqual(get_current_stock(empty_mi), Decimal("0"))

    def test_has_approved_initial_count(self):
        self.assertFalse(has_approved_initial_count(self.mi))
        self._tx(
            ttype=TransactionType.INITIAL_COUNT,
            status=TransactionStatus.APPROVED,
            delta=10,
            qin=10,
        )
        self.assertTrue(has_approved_initial_count(self.mi))


class AccessibleManagedItemsTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi_skin = create_managed_item(item=cls.item, department=cls.dept_skin)
        cls.mi_treatment = create_managed_item(
            item=cls.item, department=cls.dept_treatment
        )
        # 탕전실 (active_for_inventory=False)
        cls.mi_decoction = create_managed_item(
            item=cls.item, department=cls.dept_decoction
        )

    def test_staff_scope(self):
        """6.6 get_accessible_managed_items STAFF 범위 테스트"""
        qs = get_accessible_managed_items(self.staff_skin)
        self.assertIn(self.mi_skin, qs)
        self.assertNotIn(self.mi_treatment, qs)

    def test_manager_scope(self):
        """6.7 get_accessible_managed_items MANAGER 범위 테스트"""
        qs = get_accessible_managed_items(self.manager)
        self.assertIn(self.mi_skin, qs)
        self.assertIn(self.mi_treatment, qs)

    def test_inactive_inventory_department_excluded(self):
        """6.8 active_for_inventory=False 부서 제외 테스트"""
        # MANAGER 라도 탕전실 관리품목은 제외된다.
        qs = get_accessible_managed_items(self.manager)
        self.assertNotIn(self.mi_decoction, qs)


class LowStockTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item_low = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.item_ok = create_item("니들 30G", category=ItemCategory.MEDICAL_SUPPLY)
        # 최소재고 10, 현재고 5 → 부족
        cls.mi_low = create_managed_item(
            item=cls.item_low, department=cls.dept_skin, minimum_stock=10
        )
        create_stock_transaction(
            managed_item=cls.mi_low,
            transaction_type=TransactionType.IN,
            created_by=cls.staff_skin,
            status=TransactionStatus.APPROVED,
            quantity_input=5,
            quantity_delta=5,
        )
        # 최소재고 3, 현재고 20 → 충분
        cls.mi_ok = create_managed_item(
            item=cls.item_ok, department=cls.dept_skin, minimum_stock=3
        )
        create_stock_transaction(
            managed_item=cls.mi_ok,
            transaction_type=TransactionType.IN,
            created_by=cls.staff_skin,
            status=TransactionStatus.APPROVED,
            quantity_input=20,
            quantity_delta=20,
        )

    def test_low_stock_listed(self):
        """6.9 최소재고 이하 품목 조회 테스트"""
        qs = get_low_stock_managed_items(self.staff_skin)
        self.assertIn(self.mi_low, qs)

    def test_above_minimum_excluded(self):
        """6.10 최소재고 초과 품목 제외 테스트"""
        qs = get_low_stock_managed_items(self.staff_skin)
        self.assertNotIn(self.mi_ok, qs)
