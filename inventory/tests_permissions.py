from datetime import timedelta

from django.utils import timezone

from core.factories import (
    BaseFixtureTestCase,
    create_item,
    create_managed_item,
    create_stock_transaction,
)
from inventory.models import (
    ItemCategory,
    StockTransaction,
    TransactionStatus,
    TransactionType,
)
from inventory.permissions import can_access_managed_item, can_cancel_transaction


class CanAccessManagedItemTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi_skin = create_managed_item(item=cls.item, department=cls.dept_skin)
        cls.mi_treatment = create_managed_item(
            item=cls.item, department=cls.dept_treatment
        )

    def test_staff_own_department(self):
        self.assertTrue(can_access_managed_item(self.staff_skin, self.mi_skin))

    def test_staff_other_department(self):
        self.assertFalse(can_access_managed_item(self.staff_skin, self.mi_treatment))

    def test_team_leader_own_department(self):
        self.assertTrue(can_access_managed_item(self.team_leader_skin, self.mi_skin))

    def test_manager_any_department(self):
        self.assertTrue(can_access_managed_item(self.manager, self.mi_skin))
        self.assertTrue(can_access_managed_item(self.manager, self.mi_treatment))


class CanCancelTransactionTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi_skin = create_managed_item(item=cls.item, department=cls.dept_skin)
        cls.mi_treatment = create_managed_item(
            item=cls.item, department=cls.dept_treatment
        )

    def _make_tx(
        self,
        *,
        created_by,
        managed_item,
        ttype=TransactionType.IN,
        status=TransactionStatus.APPROVED,
        days_ago=0,
    ):
        tx = create_stock_transaction(
            managed_item=managed_item,
            transaction_type=ttype,
            created_by=created_by,
            status=status,
            quantity_input=1,
            quantity_delta=1,
        )
        if days_ago:
            past = timezone.now() - timedelta(days=days_ago)
            # auto_now_add 우회: 과거 created_at 강제 설정
            StockTransaction.objects.filter(pk=tx.pk).update(created_at=past)
            tx.refresh_from_db()
        return tx

    # --- STAFF ---
    def test_staff_own_today_approved(self):
        tx = self._make_tx(created_by=self.staff_skin, managed_item=self.mi_skin)
        self.assertTrue(can_cancel_transaction(self.staff_skin, tx))

    def test_staff_other_user_tx(self):
        tx = self._make_tx(
            created_by=self.team_leader_skin, managed_item=self.mi_skin
        )
        self.assertFalse(can_cancel_transaction(self.staff_skin, tx))

    def test_staff_previous_day(self):
        tx = self._make_tx(
            created_by=self.staff_skin, managed_item=self.mi_skin, days_ago=1
        )
        self.assertFalse(can_cancel_transaction(self.staff_skin, tx))

    # --- TEAM_LEADER ---
    def test_team_leader_own_department_today(self):
        tx = self._make_tx(created_by=self.staff_skin, managed_item=self.mi_skin)
        self.assertTrue(can_cancel_transaction(self.team_leader_skin, tx))

    def test_team_leader_other_department(self):
        tx = self._make_tx(
            created_by=self.staff_treatment, managed_item=self.mi_treatment
        )
        self.assertFalse(can_cancel_transaction(self.team_leader_skin, tx))

    # --- MANAGER / ADMIN ---
    def test_manager_any_department(self):
        tx = self._make_tx(
            created_by=self.staff_treatment, managed_item=self.mi_treatment
        )
        self.assertTrue(can_cancel_transaction(self.manager, tx))

    def test_admin_any_department(self):
        tx = self._make_tx(
            created_by=self.staff_treatment, managed_item=self.mi_treatment
        )
        self.assertTrue(can_cancel_transaction(self.admin, tx))

    def test_manager_previous_day_still_ok(self):
        tx = self._make_tx(
            created_by=self.staff_skin, managed_item=self.mi_skin, days_ago=3
        )
        self.assertTrue(can_cancel_transaction(self.manager, tx))

    # --- 거래 유형 제한 ---
    def test_initial_count_not_cancelable(self):
        tx = self._make_tx(
            created_by=self.staff_skin,
            managed_item=self.mi_skin,
            ttype=TransactionType.INITIAL_COUNT,
        )
        self.assertFalse(can_cancel_transaction(self.manager, tx))

    def test_adjustment_not_cancelable(self):
        tx = self._make_tx(
            created_by=self.staff_skin,
            managed_item=self.mi_skin,
            ttype=TransactionType.ADJUSTMENT,
        )
        self.assertFalse(can_cancel_transaction(self.manager, tx))

    # --- 상태 제한 ---
    def test_pending_not_cancelable(self):
        tx = self._make_tx(
            created_by=self.staff_skin,
            managed_item=self.mi_skin,
            status=TransactionStatus.PENDING,
        )
        self.assertFalse(can_cancel_transaction(self.manager, tx))

    def test_rejected_not_cancelable(self):
        tx = self._make_tx(
            created_by=self.staff_skin,
            managed_item=self.mi_skin,
            status=TransactionStatus.REJECTED,
        )
        self.assertFalse(can_cancel_transaction(self.manager, tx))

    def test_canceled_not_cancelable(self):
        tx = self._make_tx(
            created_by=self.staff_skin,
            managed_item=self.mi_skin,
            status=TransactionStatus.CANCELED,
        )
        self.assertFalse(can_cancel_transaction(self.manager, tx))
