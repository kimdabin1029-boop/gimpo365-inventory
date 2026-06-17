from django.test import Client
from django.urls import reverse

from core.factories import BaseFixtureTestCase, create_item, create_managed_item
from inventory.models import (
    ItemCategory,
    StockTransaction,
    TransactionStatus,
    TransactionType,
)
from inventory.selectors import get_current_stock
from inventory.services import (
    create_stock_in,
    request_initial_count,
)


class StateViewTestBase(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)


class PendingListAccessTest(StateViewTestBase):
    def test_staff_cannot_access_pending(self):
        """15.2 STAFF는 pending 화면 접근 불가"""
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:pending_list"))
        self.assertEqual(resp.status_code, 403)

    def test_manager_can_access_pending(self):
        """15.3 MANAGER는 pending 화면 접근 가능"""
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:pending_list"))
        self.assertEqual(resp.status_code, 200)


class DirectAccessGuardTest(StateViewTestBase):
    def test_cancel_url_direct_access_blocked(self):
        """15.4 cancel URL 직접 접근 차단 (취소 권한 없는 사용자)"""
        # team_leader_skin 이 등록한 IN → staff_skin 은 취소 불가
        tx = create_stock_in(
            user=self.team_leader_skin, managed_item=self.mi, quantity=10
        )
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:cancel", args=[tx.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_approve_url_direct_access_blocked(self):
        """15.5 approve URL 직접 접근 차단 (STAFF)"""
        ic = request_initial_count(
            user=self.staff_skin, managed_item=self.mi, quantity=20
        )  # PENDING
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:approve", args=[ic.pk]))
        self.assertEqual(resp.status_code, 403)


class GetVsPostTest(StateViewTestBase):
    def test_get_does_not_change_state(self):
        """15.6 GET은 상태 변경하지 않음"""
        ic = request_initial_count(
            user=self.staff_skin, managed_item=self.mi, quantity=20
        )  # PENDING
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:approve", args=[ic.pk]))
        self.assertEqual(resp.status_code, 200)  # 확인 Form 렌더
        ic.refresh_from_db()
        self.assertEqual(ic.status, TransactionStatus.PENDING)

    def test_post_changes_state(self):
        """15.7 POST만 상태 변경 수행"""
        ic = request_initial_count(
            user=self.staff_skin, managed_item=self.mi, quantity=20
        )
        self.client.force_login(self.manager)
        resp = self.client.post(reverse("inventory:approve", args=[ic.pk]))
        self.assertEqual(resp.status_code, 302)  # 성공 후 redirect
        ic.refresh_from_db()
        self.assertEqual(ic.status, TransactionStatus.APPROVED)
        self.assertEqual(get_current_stock(self.mi), 20)


class CsrfTest(StateViewTestBase):
    def test_post_without_csrf_blocked(self):
        """15.8 CSRF 없는 POST 차단"""
        ic = request_initial_count(
            user=self.staff_skin, managed_item=self.mi, quantity=20
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.manager)
        resp = csrf_client.post(reverse("inventory:approve", args=[ic.pk]))
        self.assertEqual(resp.status_code, 403)
        ic.refresh_from_db()
        self.assertEqual(ic.status, TransactionStatus.PENDING)


class CancelLinkRenderTest(StateViewTestBase):
    def test_cancel_link_points_to_cancel_url(self):
        """TASK 15 cancel marker 가 실제 cancel URL 로 연결됨"""
        in_tx = create_stock_in(user=self.manager, managed_item=self.mi, quantity=10)
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:transaction_list"))
        self.assertContains(resp, reverse("inventory:cancel", args=[in_tx.pk]))


class BulkApproveViewTest(StateViewTestBase):
    def test_bulk_approve_via_post(self):
        item2 = create_item("니들 30G", category=ItemCategory.MEDICAL_SUPPLY)
        mi2 = create_managed_item(item=item2, department=self.dept_skin)
        ic1 = request_initial_count(
            user=self.staff_skin, managed_item=self.mi, quantity=20
        )
        ic2 = request_initial_count(
            user=self.staff_skin, managed_item=mi2, quantity=30
        )
        self.client.force_login(self.manager)
        resp = self.client.post(
            reverse("inventory:bulk_approve"),
            data={"selected": [ic1.pk, ic2.pk]},
        )
        self.assertEqual(resp.status_code, 302)
        ic1.refresh_from_db()
        ic2.refresh_from_db()
        self.assertEqual(ic1.status, TransactionStatus.APPROVED)
        self.assertEqual(ic2.status, TransactionStatus.APPROVED)

    def test_bulk_approve_get_does_not_change_state(self):
        ic = request_initial_count(
            user=self.staff_skin, managed_item=self.mi, quantity=20
        )
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:bulk_approve"))
        self.assertEqual(resp.status_code, 302)  # pending 으로 redirect, 변경 없음
        ic.refresh_from_db()
        self.assertEqual(ic.status, TransactionStatus.PENDING)
