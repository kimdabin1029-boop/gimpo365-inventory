from django.urls import reverse

from core.factories import BaseFixtureTestCase, create_item, create_managed_item
from inventory.models import ItemCategory
from inventory.services import create_stock_in, request_adjustment


class CancelConfirmScreenTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)
        cls.tx = create_stock_in(user=cls.manager, managed_item=cls.mi, quantity=10)

    def test_cancel_confirm_hides_internal_id(self):
        """1-1: 취소 확인 화면에 거래번호/내부 id 미표시, 거래이력 용어 사용"""
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:cancel", args=[self.tx.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "거래 번호")
        self.assertNotContains(resp, "거래번호")
        self.assertContains(resp, "거래일자")
        self.assertContains(resp, "거래유형")
        self.assertContains(resp, "입력자")


class AdjustmentListColumnsTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)
        create_stock_in(user=cls.manager, managed_item=cls.mi, quantity=10)
        request_adjustment(
            user=cls.team_leader_skin, managed_item=cls.mi, actual_quantity=7,
            reason="실물 재고 부족",
        )

    def test_no_input_datetime_column_but_has_requester(self):
        """1-2: 실사조정 내역 메인 표에서 입력일시 컬럼 제거, 요청자 표시"""
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:adjustment_list"))
        self.assertNotContains(resp, "<th>입력일시</th>")
        self.assertContains(resp, "요청자")


class InfoPanelMinStockTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(
            item=cls.item, department=cls.dept_skin, minimum_stock=10
        )

    def test_create_form_panel_has_no_min_stock(self):
        """1-4: 입고 입력 화면 정보 패널에 최소재고 미표시"""
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:stock_in_new"))
        self.assertNotContains(resp, "최소재고")

    def test_stock_overview_still_shows_min_stock(self):
        """재고현황에는 최소재고 유지"""
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:stock_list"))
        self.assertContains(resp, "최소재고")
