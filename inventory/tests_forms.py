from datetime import timedelta

from django.utils import timezone

from core.factories import BaseFixtureTestCase, create_item, create_managed_item
from inventory.forms import (
    AdjustmentRequestForm,
    InitialCountForm,
    StockInForm,
    StockOutForm,
)
from inventory.models import ItemCategory


class FormFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi_skin = create_managed_item(item=cls.item, department=cls.dept_skin)
        cls.mi_treatment = create_managed_item(
            item=cls.item, department=cls.dept_treatment
        )


class UserAwareQuerysetTest(FormFixtureMixin, BaseFixtureTestCase):
    def _assert_scoped(self, form):
        qs = form.fields["managed_item"].queryset
        self.assertIn(self.mi_skin, qs)
        self.assertNotIn(self.mi_treatment, qs)

    def test_stock_in_form_user_aware(self):
        """14.1 StockInForm user-aware queryset 테스트"""
        self._assert_scoped(StockInForm(user=self.staff_skin))

    def test_stock_out_form_user_aware(self):
        """14.2 StockOutForm user-aware queryset 테스트"""
        self._assert_scoped(StockOutForm(user=self.staff_skin))

    def test_adjustment_form_user_aware(self):
        """14.3 AdjustmentRequestForm user-aware queryset 테스트"""
        self._assert_scoped(AdjustmentRequestForm(user=self.staff_skin))

    def test_initial_count_form_user_aware(self):
        """14.4 InitialCountForm user-aware queryset 테스트"""
        self._assert_scoped(InitialCountForm(user=self.staff_skin))

    def test_manager_sees_all_departments(self):
        qs = StockInForm(user=self.manager).fields["managed_item"].queryset
        self.assertIn(self.mi_skin, qs)
        self.assertIn(self.mi_treatment, qs)


class UnitPriceVisibilityTest(FormFixtureMixin, BaseFixtureTestCase):
    def test_staff_unit_price_removed(self):
        """14.5 STAFF StockInForm unit_price 제거 테스트"""
        form = StockInForm(user=self.staff_skin)
        self.assertNotIn("unit_price", form.fields)

    def test_team_leader_unit_price_present(self):
        """14.6 TEAM_LEADER StockInForm unit_price 표시 테스트"""
        form = StockInForm(user=self.team_leader_skin)
        self.assertIn("unit_price", form.fields)

    def test_manager_unit_price_present(self):
        form = StockInForm(user=self.manager)
        self.assertIn("unit_price", form.fields)


class OccurredAtTest(FormFixtureMixin, BaseFixtureTestCase):
    def test_occurred_at_default(self):
        """14.7 occurred_at 기본값 테스트"""
        form = StockInForm(user=self.staff_skin)
        self.assertIs(form.fields["occurred_at"].initial, timezone.now)

    def test_occurred_at_future_blocked(self):
        """14.8 occurred_at 미래 날짜 차단 테스트"""
        future = timezone.localtime(timezone.now() + timedelta(days=1)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        data = {
            "managed_item": self.mi_skin.pk,
            "quantity": "5",
            "occurred_at": future,
        }
        form = StockInForm(user=self.staff_skin, data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("occurred_at", form.errors)

    def test_valid_form_now(self):
        now = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S")
        data = {
            "managed_item": self.mi_skin.pk,
            "quantity": "5",
            "occurred_at": now,
        }
        form = StockInForm(user=self.staff_skin, data=data)
        self.assertTrue(form.is_valid(), form.errors)
