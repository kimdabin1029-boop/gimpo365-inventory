"""입고/출고/실사조정 화면 부서 필터 (MANAGER/ADMIN 전용) 테스트. (v0.2.2 후속)

- MANAGER/ADMIN 에게만 부서 필터 노출
- STAFF/TEAM_LEADER 에게는 숨김 + 기존 권한 범위 유지(서버 범위 불변)
"""

from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from core.factories import (
    BaseFixtureTestCase,
    approve_initial_count,
    create_item,
    create_managed_item,
)
from inventory.forms import AdjustmentRequestForm, StockInForm, StockOutForm
from inventory.models import ItemCategory, StockTransaction, TransactionType


class DeptFilterFixture:
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item1 = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.item2 = create_item("니들 30G", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi_skin = create_managed_item(item=cls.item1, department=cls.dept_skin)
        cls.mi_treat = create_managed_item(item=cls.item2, department=cls.dept_treatment)
        approve_initial_count(cls.mi_skin, created_by=cls.manager)
        approve_initial_count(cls.mi_treat, created_by=cls.manager)


class DeptFilterFieldTest(DeptFilterFixture, BaseFixtureTestCase):
    def test_manager_forms_have_department_filter(self):
        for form_cls in (StockInForm, StockOutForm, AdjustmentRequestForm):
            form = form_cls(user=self.manager)
            self.assertIn("department", form.fields, form_cls.__name__)

    def test_admin_forms_have_department_filter(self):
        form = StockInForm(user=self.admin)
        self.assertIn("department", form.fields)

    def test_staff_forms_no_department_filter(self):
        for form_cls in (StockInForm, StockOutForm, AdjustmentRequestForm):
            form = form_cls(user=self.staff_skin)
            self.assertNotIn("department", form.fields, form_cls.__name__)

    def test_team_leader_forms_no_department_filter(self):
        for form_cls in (StockInForm, StockOutForm, AdjustmentRequestForm):
            form = form_cls(user=self.team_leader_skin)
            self.assertNotIn("department", form.fields, form_cls.__name__)

    def test_staff_managed_item_queryset_not_widened(self):
        # 서버 권한 범위 불변: STAFF 는 여전히 본인 부서 품목만 후보로 가진다.
        form = StockInForm(user=self.staff_skin)
        qs = form.fields["managed_item"].queryset
        self.assertIn(self.mi_skin, qs)
        self.assertNotIn(self.mi_treat, qs)

    def test_manager_department_queryset_active_only(self):
        form = StockInForm(user=self.manager)
        dept_qs = form.fields["department"].queryset
        # 재고관리 대상 부서만 (탕전실 등 active_for_inventory=False 제외)
        self.assertIn(self.dept_skin, dept_qs)
        self.assertNotIn(self.dept_decoction, dept_qs)


class DeptFilterViewTest(DeptFilterFixture, BaseFixtureTestCase):
    def test_manager_page_shows_filter_and_dept_data(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:stock_in_new"))
        self.assertContains(resp, 'name="department"')
        # 관리품목 옵션에 부서 id 가 실려 클라이언트 필터가 동작한다.
        self.assertContains(resp, "data-dept-id=")

    def test_staff_page_hides_filter(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:stock_in_new"))
        self.assertNotContains(resp, 'name="department"')

    def test_manager_submit_ignores_department_and_creates_tx(self):
        # 부서 필터는 UX 용 → service 로 전달되지 않는다. 정상 입고 생성 확인.
        self.client.force_login(self.manager)
        resp = self.client.post(
            reverse("inventory:stock_in_new"),
            data={
                "department": self.dept_skin.pk,  # UX 필터값 (무시됨)
                "managed_item": self.mi_skin.pk,
                "quantity": "5",
                "occurred_at": timezone.localdate().strftime("%Y-%m-%d"),
                "unit_price": "1000",
                "no_expiration": "on",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "입고가 등록되었습니다.")
        self.assertTrue(
            StockTransaction.objects.filter(
                managed_item=self.mi_skin, transaction_type=TransactionType.IN,
                quantity_delta=Decimal("5"),
            ).exists()
        )
