from datetime import date, timedelta

from django import forms as djforms
from django.utils import timezone

from core.factories import (
    BaseFixtureTestCase,
    create_item,
    create_managed_item,
    create_stock_transaction,
)
from inventory.forms import (
    ADJUSTMENT_REASON_CHOICES,
    AdjustmentRequestForm,
    InitialCountForm,
    StockInForm,
    StockOutForm,
)
from inventory.models import ItemCategory, TransactionStatus, TransactionType


class FormFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item(
            "거즈 5x5",
            category=ItemCategory.MEDICAL_SUPPLY,
            specification="멸균, 1팩 10매",
        )
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
    def test_occurred_at_default_today(self):
        """14.7 입고일자 기본값(오늘) 테스트 (v0.1.1: 날짜 입력)"""
        form = StockInForm(user=self.staff_skin)
        self.assertIs(form.fields["occurred_at"].initial, timezone.localdate)

    def test_occurred_at_future_blocked(self):
        """14.8 입고일자 미래 날짜 차단 테스트"""
        future = (timezone.localdate() + timedelta(days=1)).strftime("%Y-%m-%d")
        data = {
            "managed_item": self.mi_skin.pk,
            "quantity": "5",
            "occurred_at": future,
        }
        form = StockInForm(user=self.staff_skin, data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("occurred_at", form.errors)

    def test_valid_form_today(self):
        today = timezone.localdate().strftime("%Y-%m-%d")
        data = {
            "managed_item": self.mi_skin.pk,
            "quantity": "5",
            "occurred_at": today,
        }
        form = StockInForm(user=self.staff_skin, data=data)
        self.assertTrue(form.is_valid(), form.errors)
        # 날짜 입력이 datetime 으로 변환되어 service 로 전달된다.
        from datetime import datetime as _dt

        self.assertIsInstance(form.cleaned_data["occurred_at"], _dt)

    def test_past_date_allowed(self):
        past = (timezone.localdate() - timedelta(days=3)).strftime("%Y-%m-%d")
        data = {
            "managed_item": self.mi_skin.pk,
            "quantity": "5",
            "occurred_at": past,
        }
        form = StockInForm(user=self.staff_skin, data=data)
        self.assertTrue(form.is_valid(), form.errors)


class V011UsabilityTest(FormFixtureMixin, BaseFixtureTestCase):
    def test_stock_in_occurred_at_label_is_ipgo_date(self):
        """2. 입고등록: occurred_at 라벨 '입고일자' + 날짜 입력"""
        form = StockInForm(user=self.staff_skin)
        field = form.fields["occurred_at"]
        self.assertEqual(field.label, "입고일자")
        self.assertIsInstance(field, djforms.DateField)
        self.assertEqual(field.widget.input_type, "date")

    def test_expiration_date_is_date_input(self):
        """3. 입고등록: 유통기한 date input"""
        form = StockInForm(user=self.staff_skin)
        field = form.fields["expiration_date"]
        self.assertEqual(field.label, "유통기한")
        self.assertFalse(field.required)
        self.assertEqual(field.widget.input_type, "date")

    def test_quantity_step_is_one(self):
        """4. 수량 input step=1 (4개 폼)"""
        forms_and_fields = [
            (StockInForm(user=self.staff_skin), "quantity"),
            (StockOutForm(user=self.staff_skin), "quantity"),
            (InitialCountForm(user=self.staff_skin), "quantity"),
            (AdjustmentRequestForm(user=self.staff_skin), "actual_quantity"),
        ]
        for form, fname in forms_and_fields:
            attrs = form.fields[fname].widget.attrs
            self.assertEqual(attrs.get("step"), "1", f"{type(form).__name__}.{fname}")

    def test_specification_in_option_label(self):
        """5. 관리품목 선택지 라벨에 specification/부서/단위 노출"""
        field = StockInForm(user=self.staff_skin).fields["managed_item"]
        label = field.label_from_instance(self.mi_skin)
        self.assertIn("거즈 5x5", label)
        self.assertIn("멸균, 1팩 10매", label)  # specification
        self.assertIn("피부실", label)
        self.assertIn("EA", label)

    def test_stock_out_option_label_shows_current_stock(self):
        """6. 출고등록: 선택 품목 현재고 라벨 표시"""
        create_stock_transaction(
            managed_item=self.mi_skin,
            transaction_type=TransactionType.IN,
            created_by=self.staff_skin,
            status=TransactionStatus.APPROVED,
            quantity_input=12,
            quantity_delta=12,
        )
        field = StockOutForm(user=self.staff_skin).fields["managed_item"]
        obj = field.queryset.get(pk=self.mi_skin.pk)
        label = field.label_from_instance(obj)
        self.assertIn("현재고", label)
        self.assertIn("12", label)

    def test_adjustment_reason_is_choices(self):
        """7. 실사조정 사유 드롭다운(choices)"""
        field = AdjustmentRequestForm(user=self.staff_skin).fields["reason"]
        self.assertIsInstance(field, djforms.ChoiceField)
        values = [c[0] for c in field.choices]
        for expected in ["실물 재고 부족", "기타"]:
            self.assertIn(expected, values)
        self.assertEqual(values, [c[0] for c in ADJUSTMENT_REASON_CHOICES])

    def test_out_form_user_aware_preserved(self):
        """8. 검색 개선 후에도 user-aware queryset 유지 (타 부서 미노출)"""
        qs = StockOutForm(user=self.staff_skin).fields["managed_item"].queryset
        self.assertIn(self.mi_skin, qs)
        self.assertNotIn(self.mi_treatment, qs)
