from django.urls import reverse
from django.utils import timezone

from core.factories import (
    BaseFixtureTestCase,
    create_item,
    create_managed_item,
)
from inventory.models import (
    ItemCategory,
    StockTransaction,
    TransactionStatus,
    TransactionType,
)
from inventory.selectors import get_current_stock
from inventory.services import (
    approve_transaction,
    create_stock_in,
    request_adjustment,
    request_initial_count,
)


def _now_str():
    return timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S")


class DashboardAccessTest(BaseFixtureTestCase):
    def test_anonymous_redirected_to_login(self):
        """15.1 비로그인 사용자는 inventory 화면 접근 불가 (로그인 redirect)"""
        resp = self.client.get(reverse("inventory:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:login"), resp.url)

    def test_logged_in_user_can_access(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:dashboard"))
        self.assertEqual(resp.status_code, 200)


class AdminButtonVisibilityTest(BaseFixtureTestCase):
    def test_admin_button_shown_for_staff_user(self):
        """16.8 Admin 버튼 표시 테스트 — is_staff=True(admin)에게만 노출"""
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("inventory:dashboard"))
        self.assertContains(resp, "django-admin-link")

    def test_admin_button_hidden_for_non_staff(self):
        """is_staff=False 인 STAFF / MANAGER 에게는 미노출"""
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:dashboard"))
        self.assertNotContains(resp, "django-admin-link")

        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:dashboard"))
        self.assertNotContains(resp, "django-admin-link")


class ListViewAccessTest(BaseFixtureTestCase):
    def test_anonymous_redirected(self):
        for name in ("stock_list", "low_stock", "transaction_list"):
            resp = self.client.get(reverse(f"inventory:{name}"))
            self.assertEqual(resp.status_code, 302)
            self.assertIn(reverse("accounts:login"), resp.url)

    def test_logged_in_access(self):
        self.client.force_login(self.staff_skin)
        for name in ("stock_list", "low_stock", "transaction_list"):
            resp = self.client.get(reverse(f"inventory:{name}"))
            self.assertEqual(resp.status_code, 200)


class CancelButtonVisibilityTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.item2 = create_item("니들 30G", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)
        cls.mi2 = create_managed_item(item=cls.item2, department=cls.dept_skin)

    def test_initial_count_has_no_cancel_button(self):
        """18.1 승인된 INITIAL_COUNT 취소 버튼 없음"""
        ic = request_initial_count(
            user=self.manager, managed_item=self.mi2, quantity=20
        )  # 즉시 APPROVED
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:transaction_list"))
        self.assertNotContains(resp, f'id="cancel-{ic.pk}"')

    def test_adjustment_has_no_cancel_button_but_in_does(self):
        """18.2 승인된 ADJUSTMENT 취소 버튼 없음 (IN 거래는 표시)"""
        in_tx = create_stock_in(user=self.manager, managed_item=self.mi, quantity=10)
        adj = request_adjustment(
            user=self.staff_skin,
            managed_item=self.mi,
            actual_quantity=7,
            reason="실사",
        )
        approve_transaction(user=self.manager, transaction_obj=adj)  # APPROVED ADJUSTMENT

        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:transaction_list"))
        # IN(일반 거래)은 취소 버튼 표시
        self.assertContains(resp, f'id="cancel-{in_tx.pk}"')
        # ADJUSTMENT 는 취소 버튼 없음
        self.assertNotContains(resp, f'id="cancel-{adj.pk}"')


class CreateViewTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)

    def test_get_renders_form(self):
        self.client.force_login(self.staff_skin)
        for name in (
            "stock_in_new",
            "stock_out_new",
            "adjustment_new",
            "initial_count_new",
        ):
            resp = self.client.get(reverse(f"inventory:{name}"))
            self.assertEqual(resp.status_code, 200)

    def test_stock_in_stays_on_form(self):
        """15.9 입고 등록 후 같은 Form에 머무름"""
        self.client.force_login(self.staff_skin)
        resp = self.client.post(
            reverse("inventory:stock_in_new"),
            data={
                "managed_item": self.mi.pk,
                "quantity": "10",
                # v0.1.1: 입고일자는 날짜 입력
                "occurred_at": timezone.localdate().strftime("%Y-%m-%d"),
            },
        )
        # redirect 가 아니라 같은 화면(200) 유지
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "입고가 등록되었습니다.")
        # 거래가 service 를 통해 생성됨
        tx = StockTransaction.objects.get(
            managed_item=self.mi, transaction_type=TransactionType.IN
        )
        self.assertEqual(tx.status, TransactionStatus.APPROVED)
        self.assertEqual(tx.created_by, self.staff_skin)

    def test_stock_out_stays_on_form(self):
        """15.10 출고 등록 후 같은 Form에 머무름"""
        create_stock_in(user=self.staff_skin, managed_item=self.mi, quantity=10)
        self.client.force_login(self.staff_skin)
        resp = self.client.post(
            reverse("inventory:stock_out_new"),
            data={
                "managed_item": self.mi.pk,
                "transaction_type": TransactionType.OUT_USE.value,
                "quantity": "3",
                "occurred_at": timezone.localdate().strftime("%Y-%m-%d"),
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "출고가 등록되었습니다.")
        self.assertEqual(get_current_stock(self.mi), 7)

    def test_stock_out_service_error_message(self):
        """service 예외(현재고 초과 출고) 발생 시 실패 메시지 표시, 거래 미생성"""
        create_stock_in(user=self.staff_skin, managed_item=self.mi, quantity=5)
        self.client.force_login(self.staff_skin)
        resp = self.client.post(
            reverse("inventory:stock_out_new"),
            data={
                "managed_item": self.mi.pk,
                "transaction_type": TransactionType.OUT_USE.value,
                "quantity": "10",
                "occurred_at": timezone.localdate().strftime("%Y-%m-%d"),
            },
        )
        self.assertEqual(resp.status_code, 200)
        # 현재고는 그대로 5, OUT 거래는 생성되지 않음
        self.assertEqual(get_current_stock(self.mi), 5)
        self.assertFalse(
            StockTransaction.objects.filter(
                managed_item=self.mi, transaction_type=TransactionType.OUT_USE
            ).exists()
        )

    def test_create_requires_login(self):
        resp = self.client.get(reverse("inventory:stock_in_new"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:login"), resp.url)
