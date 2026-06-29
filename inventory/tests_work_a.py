from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from core.factories import (
    BaseFixtureTestCase,
    create_item,
    create_managed_item,
    create_stock_transaction,
)
from inventory.models import ItemCategory, StockTransaction, TransactionStatus, TransactionType
from inventory.permissions import can_cancel_transaction

User = get_user_model()


class DisplayNameTest(BaseFixtureTestCase):
    def test_priority_name_first(self):
        u = User.objects.create_user(username="u1", password="x", name="김다빈")
        self.assertEqual(u.display_name, "김다빈")

    def test_fallback_full_name(self):
        u = User.objects.create_user(
            username="u2", password="x", first_name="다빈", last_name="김"
        )
        # name 비어있으면 get_full_name() 사용
        self.assertEqual(u.display_name, u.get_full_name())
        self.assertNotEqual(u.display_name, "u2")

    def test_fallback_username(self):
        u = User.objects.create_user(username="u3", password="x")
        self.assertEqual(u.display_name, "u3")

    def test_navbar_shows_display_name(self):
        user = User.objects.create_user(
            username="login1", password="pw12345!", name="김다빈"
        )
        self.client.force_login(user)
        resp = self.client.get(reverse("inventory:dashboard"))
        self.assertContains(resp, "김다빈")


class AdjustmentAccessViewTest(BaseFixtureTestCase):
    def test_staff_cannot_access_adjustment(self):
        """실사조정 요청(초기재고 포함)은 STAFF 접근 차단(403)"""
        self.client.force_login(self.staff_skin)
        self.assertEqual(
            self.client.get(reverse("inventory:adjustment_new")).status_code, 403
        )

    def test_team_leader_can_access_adjustment(self):
        self.client.force_login(self.team_leader_skin)
        self.assertEqual(
            self.client.get(reverse("inventory:adjustment_new")).status_code, 200
        )

    def test_initial_count_url_redirects_to_adjustment(self):
        """기존 초기재고 URL 은 실사조정 요청으로 redirect"""
        self.client.force_login(self.team_leader_skin)
        resp = self.client.get(reverse("inventory:initial_count_new"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("inventory:adjustment_new"), resp.url)

    def test_dashboard_hides_adjustment_for_staff(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:dashboard"))
        self.assertNotContains(resp, reverse("inventory:adjustment_new"))
        self.client.force_login(self.team_leader_skin)
        resp = self.client.get(reverse("inventory:dashboard"))
        self.assertContains(resp, reverse("inventory:adjustment_new"))


class AdjustmentRoutingViewTest(BaseFixtureTestCase):
    """HOTFIX 4: 실사조정 요청 화면은 승인된 최초재고 유무에 따라 라우팅한다.

    - 승인된 최초재고 없음 → 일반 ADJUSTMENT 가 아니라 INITIAL_COUNT 로 처리
    - 승인된 최초재고 있음 → ADJUSTMENT(PENDING) 로 처리
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)

    def _post(self, *, quantity, reason=""):
        return self.client.post(
            reverse("inventory:adjustment_new"),
            data={
                "managed_item": self.mi.pk,
                "actual_quantity": str(quantity),
                "occurred_at": timezone.localdate().strftime("%Y-%m-%d"),
                "reason": reason,
                "memo": "",
            },
        )

    def test_routes_to_initial_count_when_no_approved(self):
        """승인된 최초재고가 없으면 INITIAL_COUNT 로만 처리(일반 ADJUSTMENT 생성 안 함)."""
        self.client.force_login(self.team_leader_skin)
        resp = self._post(quantity=20)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "최초 재고 입력이 등록되었습니다.")
        self.assertTrue(
            self.mi.stock_transactions.filter(
                transaction_type=TransactionType.INITIAL_COUNT,
                status=TransactionStatus.PENDING,
            ).exists()
        )
        self.assertFalse(
            self.mi.stock_transactions.filter(
                transaction_type=TransactionType.ADJUSTMENT
            ).exists()
        )

    def test_routes_to_adjustment_when_approved_exists(self):
        """승인된 최초재고가 있으면 ADJUSTMENT(PENDING) 로 처리."""
        create_stock_transaction(
            managed_item=self.mi,
            transaction_type=TransactionType.INITIAL_COUNT,
            created_by=self.manager,
            status=TransactionStatus.APPROVED,
            quantity_input=10,
            quantity_delta=10,
        )
        self.client.force_login(self.team_leader_skin)
        resp = self._post(quantity=7, reason="실물 재고 부족")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "실사조정 요청이 등록되었습니다. (승인 대기)")
        self.assertTrue(
            self.mi.stock_transactions.filter(
                transaction_type=TransactionType.ADJUSTMENT,
                status=TransactionStatus.PENDING,
            ).exists()
        )


class CancelBasisTest(BaseFixtureTestCase):
    """A-4: 직접 취소 가능 여부는 입력일시(created_at) 기준 당일."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)

    def _tx(self, *, created_days_ago=0, occurred_days_ago=0):
        tx = create_stock_transaction(
            managed_item=self.mi,
            transaction_type=TransactionType.IN,
            created_by=self.staff_skin,
            status=TransactionStatus.APPROVED,
            quantity_input=1,
            quantity_delta=1,
            occurred_at=timezone.now() - timedelta(days=occurred_days_ago),
        )
        if created_days_ago:
            StockTransaction.objects.filter(pk=tx.pk).update(
                created_at=timezone.now() - timedelta(days=created_days_ago)
            )
            tx.refresh_from_db()
        return tx

    def test_today_input_cancelable(self):
        """1. STAFF 오늘 입력 일반 거래는 직접 취소 가능"""
        tx = self._tx(created_days_ago=0, occurred_days_ago=0)
        self.assertTrue(can_cancel_transaction(self.staff_skin, tx))

    def test_yesterday_input_not_cancelable(self):
        """2. STAFF 어제 입력 일반 거래는 직접 취소 불가"""
        tx = self._tx(created_days_ago=1, occurred_days_ago=0)
        self.assertFalse(can_cancel_transaction(self.staff_skin, tx))

    def test_occurred_yesterday_but_input_today_cancelable(self):
        """3. 거래일자 어제라도 입력일시 오늘이면 취소 가능"""
        tx = self._tx(created_days_ago=0, occurred_days_ago=1)
        self.assertTrue(can_cancel_transaction(self.staff_skin, tx))

    def test_occurred_today_but_input_yesterday_not_cancelable(self):
        """3-역: 거래일자 오늘이어도 입력일시 어제면 STAFF 직접 취소 불가"""
        tx = self._tx(created_days_ago=1, occurred_days_ago=0)
        self.assertFalse(can_cancel_transaction(self.staff_skin, tx))

    def test_initial_count_and_adjustment_not_cancelable(self):
        """4. INITIAL_COUNT / ADJUSTMENT 는 직접 취소 불가"""
        for ttype in (TransactionType.INITIAL_COUNT, TransactionType.ADJUSTMENT):
            tx = create_stock_transaction(
                managed_item=self.mi,
                transaction_type=ttype,
                created_by=self.staff_skin,
                status=TransactionStatus.APPROVED,
                quantity_input=1,
                quantity_delta=1,
            )
            self.assertFalse(can_cancel_transaction(self.manager, tx))
