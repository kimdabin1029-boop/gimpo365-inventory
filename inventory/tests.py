from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.factories import (
    BaseFixtureTestCase,
    create_item,
    create_managed_item,
    create_stock_transaction,
    create_supplier,
)
from inventory.models import (
    Item,
    ItemCategory,
    ManagedItem,
    Supplier,
    TransactionStatus,
    TransactionType,
    Unit,
)


class SupplierModelTest(TestCase):
    def test_name_unique(self):
        """4.2 Supplier.name unique 테스트"""
        create_supplier(name="메디칼코리아")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                create_supplier(name="메디칼코리아")

    def test_name_strip_normalization(self):
        """4.11 Supplier.name strip 정규화 테스트"""
        supplier = create_supplier(name="  메디칼코리아  ")
        supplier.refresh_from_db()
        self.assertEqual(supplier.name, "메디칼코리아")


class ItemModelTest(TestCase):
    def test_name_unique(self):
        """4.3 Item.name unique 테스트"""
        create_item("거즈 5x5")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                create_item("거즈 5x5")

    def test_specification_not_unique(self):
        """4.4 Item.specification 은 unique 기준이 아님 테스트"""
        create_item("거즈 5x5", specification="1BOX(10EA)")
        # 같은 specification 이지만 name 이 다르면 생성 가능해야 한다.
        create_item("거즈 10x10", specification="1BOX(10EA)")
        self.assertEqual(Item.objects.filter(specification="1BOX(10EA)").count(), 2)

    def test_name_strip_normalization(self):
        """4.11 Item.name strip 정규화 테스트"""
        item = create_item("  니들 30G  ")
        item.refresh_from_db()
        self.assertEqual(item.name, "니들 30G")


class ManagedItemModelTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item_gauze = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)

    def test_department_item_unique(self):
        """4.5 ManagedItem department + item unique 테스트"""
        create_managed_item(item=self.item_gauze, department=self.dept_skin)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                create_managed_item(item=self.item_gauze, department=self.dept_skin)

    def test_same_item_allowed_in_different_departments(self):
        """4.6 다른 부서의 같은 Item 허용 테스트"""
        mi_skin = create_managed_item(item=self.item_gauze, department=self.dept_skin)
        mi_treatment = create_managed_item(
            item=self.item_gauze, department=self.dept_treatment
        )
        self.assertNotEqual(mi_skin.pk, mi_treatment.pk)
        self.assertEqual(
            ManagedItem.objects.filter(item=self.item_gauze).count(), 2
        )

    def test_defaults(self):
        mi = create_managed_item(item=self.item_gauze, department=self.dept_skin)
        self.assertEqual(mi.unit, Unit.EA)
        self.assertEqual(mi.minimum_stock, 0)
        self.assertIsNone(mi.default_supplier)
        self.assertTrue(mi.is_active)


class StockTransactionConstraintTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)

    def _tx(self, **kwargs):
        kwargs.setdefault("managed_item", self.mi)
        kwargs.setdefault("created_by", self.staff_skin)
        return create_stock_transaction(**kwargs)

    def test_approved_initial_count_uniqueness(self):
        """4.7 APPROVED INITIAL_COUNT 유일성 테스트"""
        self._tx(
            transaction_type=TransactionType.INITIAL_COUNT,
            status=TransactionStatus.APPROVED,
            quantity_input=10,
            quantity_delta=10,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._tx(
                    transaction_type=TransactionType.INITIAL_COUNT,
                    status=TransactionStatus.APPROVED,
                    quantity_input=5,
                    quantity_delta=5,
                )

    def test_pending_initial_count_duplicate_allowed(self):
        """4.8 PENDING INITIAL_COUNT 중복 허용 테스트"""
        self._tx(
            transaction_type=TransactionType.INITIAL_COUNT,
            status=TransactionStatus.PENDING,
            quantity_input=10,
            quantity_delta=10,
        )
        # PENDING 은 partial unique 조건(APPROVED)에 걸리지 않으므로 중복 허용
        self._tx(
            transaction_type=TransactionType.INITIAL_COUNT,
            status=TransactionStatus.PENDING,
            quantity_input=7,
            quantity_delta=7,
        )
        self.assertEqual(
            self.mi.stock_transactions.filter(
                transaction_type=TransactionType.INITIAL_COUNT,
                status=TransactionStatus.PENDING,
            ).count(),
            2,
        )

    def test_quantity_input_negative_blocked(self):
        """4.9 quantity_input 음수 차단 테스트"""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._tx(
                    transaction_type=TransactionType.IN,
                    status=TransactionStatus.APPROVED,
                    quantity_input=-1,
                    quantity_delta=-1,
                )

    def test_quantity_delta_negative_allowed(self):
        """4.10 quantity_delta 음수 허용 테스트"""
        tx = self._tx(
            transaction_type=TransactionType.OUT_USE,
            status=TransactionStatus.APPROVED,
            quantity_input=5,
            quantity_delta=-5,
        )
        self.assertEqual(tx.quantity_delta, -5)


class ManagedItemUnitChangeTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)

    def test_unit_change_allowed_without_approved_tx(self):
        """5.1 APPROVED 거래가 없으면 unit 변경 가능"""
        mi = create_managed_item(
            item=self.item, department=self.dept_skin, unit=Unit.EA
        )
        mi.unit = Unit.BOX
        mi.full_clean()  # ValidationError 가 발생하지 않아야 한다
        mi.save()
        mi.refresh_from_db()
        self.assertEqual(mi.unit, Unit.BOX)

    def test_unit_change_blocked_with_approved_tx(self):
        """5.2 APPROVED 거래가 있으면 unit 변경 불가"""
        mi = create_managed_item(
            item=self.item, department=self.dept_skin, unit=Unit.EA
        )
        create_stock_transaction(
            managed_item=mi,
            transaction_type=TransactionType.IN,
            created_by=self.staff_skin,
            status=TransactionStatus.APPROVED,
            quantity_input=10,
            quantity_delta=10,
        )
        mi.unit = Unit.BOX
        with self.assertRaises(ValidationError):
            mi.full_clean()

    def test_unit_change_allowed_with_pending_only(self):
        """5.3 PENDING 거래만 있으면 unit 변경 가능"""
        mi = create_managed_item(
            item=self.item, department=self.dept_skin, unit=Unit.EA
        )
        create_stock_transaction(
            managed_item=mi,
            transaction_type=TransactionType.INITIAL_COUNT,
            created_by=self.staff_skin,
            status=TransactionStatus.PENDING,
            quantity_input=10,
            quantity_delta=10,
        )
        mi.unit = Unit.BOX
        mi.full_clean()  # PENDING 만 있으므로 통과해야 한다
        mi.save()
        mi.refresh_from_db()
        self.assertEqual(mi.unit, Unit.BOX)
