from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from core.factories import (
    BaseFixtureTestCase,
    create_item,
    create_managed_item,
    create_stock_transaction,
)
from inventory.models import ItemCategory, TransactionStatus, TransactionType
from inventory.services import (
    approve_transaction,
    create_stock_in,
    reject_transaction,
    request_adjustment,
)


class TransactionDateFilterTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)
        now = timezone.now()
        # 오늘 거래
        cls.tx_today = create_stock_transaction(
            managed_item=cls.mi,
            transaction_type=TransactionType.IN,
            created_by=cls.staff_skin,
            status=TransactionStatus.APPROVED,
            quantity_input=10,
            quantity_delta=10,
            occurred_at=now,
        )
        # 10일 전 거래
        cls.tx_old = create_stock_transaction(
            managed_item=cls.mi,
            transaction_type=TransactionType.IN,
            created_by=cls.staff_skin,
            status=TransactionStatus.APPROVED,
            quantity_input=5,
            quantity_delta=5,
            occurred_at=now - timedelta(days=10),
        )

    def test_default_is_today(self):
        """3-1: 기본 기간은 오늘~오늘 (거래일자 기준)"""
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:transaction_list"))
        txs = list(resp.context["transactions"])
        self.assertIn(self.tx_today, txs)
        self.assertNotIn(self.tx_old, txs)

    def test_range_3m_includes_recent(self):
        """B-6: 최근 3개월 빠른 필터 (10일 전 거래 포함, '전체' 대체)"""
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:transaction_list"), {"range": "3m"})
        txs = list(resp.context["transactions"])
        self.assertIn(self.tx_today, txs)
        self.assertIn(self.tx_old, txs)

    def test_range_7d_excludes_old(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:transaction_list"), {"range": "7d"})
        txs = list(resp.context["transactions"])
        self.assertIn(self.tx_today, txs)
        self.assertNotIn(self.tx_old, txs)

    def test_main_table_hides_input_datetime_column(self):
        """B-1/B-4: 입력일시는 메인 표 컬럼이 아님 (헤더에 '입력일시' 컬럼 없음)"""
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:transaction_list"), {"range": "3m"})
        # 메인 표 헤더에 거래일자는 있고, 입력일시 컬럼 헤더(<th>입력일시)는 없음
        self.assertContains(resp, "<th>거래일자</th>")
        self.assertNotContains(resp, "<th>입력일시</th>")

    def test_explicit_date_range(self):
        self.client.force_login(self.manager)
        old_day = (timezone.localdate() - timedelta(days=10)).strftime("%Y-%m-%d")
        resp = self.client.get(
            reverse("inventory:transaction_list"),
            {"date_from": old_day, "date_to": old_day},
        )
        txs = list(resp.context["transactions"])
        self.assertIn(self.tx_old, txs)
        self.assertNotIn(self.tx_today, txs)


class AdjustmentListVisibilityTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)
        cls.mi_treat = create_managed_item(
            item=create_item("니들 30G", category=ItemCategory.MEDICAL_SUPPLY),
            department=cls.dept_treatment,
        )
        create_stock_in(user=cls.manager, managed_item=cls.mi, quantity=10)
        create_stock_in(user=cls.manager, managed_item=cls.mi_treat, quantity=10)
        # staff_skin 의 조정 요청 → 반려(사유 기록)
        cls.adj_skin = request_adjustment(
            user=cls.staff_skin, managed_item=cls.mi, actual_quantity=7, reason="실물 재고 부족"
        )
        reject_transaction(
            user=cls.manager, transaction_obj=cls.adj_skin, review_note="근거 불충분"
        )
        # 치료실 staff 의 조정 요청
        cls.adj_treat = request_adjustment(
            user=cls.staff_treatment, managed_item=cls.mi_treat, actual_quantity=8, reason="기타"
        )

    def test_staff_sees_only_own_requests(self):
        """3-4: STAFF 는 본인 요청만"""
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:adjustment_list"))
        txs = list(resp.context["transactions"])
        self.assertIn(self.adj_skin, txs)
        self.assertNotIn(self.adj_treat, txs)

    def test_staff_sees_review_reason(self):
        """STAFF 가 본인 요청의 반려 사유를 확인 가능"""
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:adjustment_list"))
        self.assertContains(resp, "근거 불충분")
        self.assertContains(resp, "실물 재고 부족")

    def test_team_leader_sees_department_requests(self):
        self.client.force_login(self.team_leader_skin)
        resp = self.client.get(reverse("inventory:adjustment_list"))
        txs = list(resp.context["transactions"])
        self.assertIn(self.adj_skin, txs)  # 본인 부서(피부실)
        self.assertNotIn(self.adj_treat, txs)  # 타 부서

    def test_manager_sees_all_requests(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:adjustment_list"))
        txs = list(resp.context["transactions"])
        self.assertIn(self.adj_skin, txs)
        self.assertIn(self.adj_treat, txs)
