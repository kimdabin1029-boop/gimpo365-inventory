from decimal import Decimal

from django.test import SimpleTestCase
from django.urls import reverse

from core.factories import BaseFixtureTestCase, create_item, create_managed_item
from inventory.models import ItemCategory
from inventory.templatetags.inventory_extras import qty


class QtyFilterTest(SimpleTestCase):
    def test_strips_trailing_zeros(self):
        self.assertEqual(qty(Decimal("10.000")), "10")
        self.assertEqual(qty(Decimal("10.500")), "10.5")
        self.assertEqual(qty(Decimal("10.250")), "10.25")
        self.assertEqual(qty(Decimal("10.125")), "10.125")
        self.assertEqual(qty(Decimal("0.000")), "0")
        self.assertEqual(qty(Decimal("-3.000")), "-3")

    def test_passthrough_for_blank(self):
        self.assertIsNone(qty(None))
        self.assertEqual(qty(""), "")


class TransactionListCommentTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)

    def test_template_comment_not_rendered(self):
        """1-1: 거래이력 취소 칸의 템플릿 주석이 화면에 노출되지 않는다."""
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:transaction_list"))
        self.assertNotContains(resp, "can_cancel_transaction == True")
        self.assertNotContains(resp, "INITIAL_COUNT / ADJUSTMENT 는")

    def test_stock_page_title_is_jaego_hyeonhwang(self):
        """1-2: 재고현황 표현"""
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:stock_list"))
        self.assertContains(resp, "재고현황")


class AdminIsStaffLabelTest(BaseFixtureTestCase):
    def test_is_staff_label_and_help_text(self):
        """1-4: Admin 사용자 변경 화면의 is_staff 라벨/도움말 개선"""
        self.client.force_login(self.admin)
        url = reverse("admin:accounts_user_change", args=[self.staff_skin.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Django 관리자 페이지 접근 권한")
        self.assertContains(resp, "재고관리의 STAFF 역할과는 별개입니다")
