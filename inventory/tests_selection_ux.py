from datetime import timedelta
from decimal import Decimal

from django import forms as djforms
from django.urls import reverse
from django.utils import timezone

from core.factories import (
    BaseFixtureTestCase,
    create_item,
    create_managed_item,
)
from inventory.forms import StockOutForm
from inventory.models import (
    ItemCategory,
    StockTransaction,
    TransactionType,
)
from inventory.selectors import get_current_stock
from inventory.services import create_stock_in


class OutDateTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)

    def test_out_form_date_label_and_widget(self):
        """2-3/2-4: 출고일자 날짜 입력"""
        field = StockOutForm(user=self.staff_skin).fields["occurred_at"]
        self.assertEqual(field.label, "출고일자")
        self.assertIsInstance(field, djforms.DateField)
        self.assertEqual(field.widget.input_type, "date")

    def test_out_future_date_blocked(self):
        """출고일자 미래 차단"""
        create_stock_in(user=self.manager, managed_item=self.mi, quantity=10)
        future = (timezone.localdate() + timedelta(days=1)).strftime("%Y-%m-%d")
        form = StockOutForm(
            user=self.staff_skin,
            data={
                "managed_item": self.mi.pk,
                "transaction_type": TransactionType.OUT_USE.value,
                "quantity": "1",
                "occurred_at": future,
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn("occurred_at", form.errors)

    def test_out_past_date_reflected_in_transaction(self):
        """출고일자(과거)가 거래 occurred_at 에 반영됨"""
        create_stock_in(user=self.manager, managed_item=self.mi, quantity=10)
        past = timezone.localdate() - timedelta(days=2)
        self.client.force_login(self.staff_skin)
        self.client.post(
            reverse("inventory:stock_out_new"),
            data={
                "managed_item": self.mi.pk,
                "transaction_type": TransactionType.OUT_USE.value,
                "quantity": "3",
                "occurred_at": past.strftime("%Y-%m-%d"),
            },
        )
        tx = StockTransaction.objects.get(
            managed_item=self.mi, transaction_type=TransactionType.OUT_USE
        )
        self.assertEqual(timezone.localdate(tx.occurred_at), past)
        self.assertEqual(get_current_stock(self.mi), 7)


class ManagedItemOptionsTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi_skin = create_managed_item(
            item=cls.item, department=cls.dept_skin, minimum_stock=10
        )
        cls.mi_treat = create_managed_item(item=cls.item, department=cls.dept_treatment)
        create_stock_in(user=cls.manager, managed_item=cls.mi_skin, quantity=12)

    def test_option_carries_stock_data(self):
        """2-2: 관리품목 옵션에 현재고 data-* 부여 (검색/정보패널용)"""
        form = StockOutForm(user=self.staff_skin)
        html = str(form["managed_item"])
        self.assertIn('data-stock="12"', html)
        self.assertIn('data-min="10"', html)

    def test_option_user_aware_preserved(self):
        """검색/패널 추가 후에도 권한 범위 유지 (STAFF 타 부서 옵션 없음)"""
        form = StockOutForm(user=self.staff_skin)
        html = str(form["managed_item"])
        self.assertIn(str(self.mi_skin.pk), html)
        self.assertNotIn(f'value="{self.mi_treat.pk}"', html)

    def test_out_view_shows_projected_context(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:stock_out_new"))
        self.assertTrue(resp.context["show_projected"])
        resp_in = self.client.get(reverse("inventory:stock_in_new"))
        self.assertFalse(resp_in.context["show_projected"])


class ItemListViewTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi_skin = create_managed_item(item=cls.item, department=cls.dept_skin)
        cls.mi_treat = create_managed_item(item=cls.item, department=cls.dept_treatment)

    def test_requires_login(self):
        resp = self.client.get(reverse("inventory:item_list"))
        self.assertEqual(resp.status_code, 302)

    def test_staff_sees_only_own_department(self):
        """2-5: 품목 리스트 권한 범위 (STAFF 본인 부서만)"""
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:item_list"))
        items = list(resp.context["items"])
        self.assertIn(self.mi_skin, items)
        self.assertNotIn(self.mi_treat, items)

    def test_manager_sees_all(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:item_list"))
        items = list(resp.context["items"])
        self.assertIn(self.mi_skin, items)
        self.assertIn(self.mi_treat, items)
