from django.contrib import admin as django_admin
from django.test import RequestFactory
from django.urls import reverse

from core.factories import BaseFixtureTestCase
from inventory.models import StockTransaction


class AdminAccessTest(BaseFixtureTestCase):
    def test_staff_cannot_access_admin(self):
        """16.1 일반 STAFF Admin 접근 불가"""
        self.client.force_login(self.staff_skin)
        resp = self.client.get("/admin/")
        self.assertEqual(resp.status_code, 302)  # admin 로그인으로 redirect

    def test_manager_cannot_access_admin(self):
        """16.2 MANAGER 기본 Admin 접근 불가 (is_staff=False)"""
        self.client.force_login(self.manager)
        resp = self.client.get("/admin/")
        self.assertEqual(resp.status_code, 302)

    def test_admin_can_access_admin(self):
        """16.3 ADMIN Admin 접근 가능"""
        self.client.force_login(self.admin)
        resp = self.client.get("/admin/")
        self.assertEqual(resp.status_code, 200)

    def test_user_admin_admin_only(self):
        """16.7 User Admin은 ADMIN 전용"""
        url = reverse("admin:accounts_user_changelist")
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)

        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(url).status_code, 302)


class StockTransactionAdminTest(BaseFixtureTestCase):
    @property
    def model_admin(self):
        # ModelAdmin 인스턴스는 admin.site(모듈 참조 포함)를 들고 있어
        # setUpTestData 의 deepcopy 대상이 되면 안 된다. 매 접근 시 조회한다.
        return django_admin.site._registry[StockTransaction]

    def _request(self, user):
        req = RequestFactory().get("/admin/")
        req.user = user
        return req

    def test_add_permission_false(self):
        """16.4 StockTransaction Admin add 차단"""
        self.assertFalse(self.model_admin.has_add_permission(self._request(self.admin)))

    def test_delete_permission_false(self):
        """16.5 StockTransaction Admin delete 차단"""
        self.assertFalse(
            self.model_admin.has_delete_permission(self._request(self.admin))
        )

    def test_add_view_http_forbidden(self):
        """add view 직접 접근도 차단 (403)"""
        self.client.force_login(self.admin)
        resp = self.client.get("/admin/inventory/stocktransaction/add/")
        self.assertEqual(resp.status_code, 403)

    def test_readonly_fields(self):
        """16.6 StockTransaction Admin readonly 필드 테스트"""
        required_readonly = {
            "managed_item",
            "transaction_type",
            "status",
            "quantity_input",
            "quantity_delta",
            "expected_quantity",
            "actual_quantity",
            "created_by",
            "approved_by",
            "canceled_by",
        }
        readonly = set(self.model_admin.get_readonly_fields(self._request(self.admin)))
        self.assertTrue(
            required_readonly.issubset(readonly),
            f"누락된 readonly 필드: {required_readonly - readonly}",
        )
