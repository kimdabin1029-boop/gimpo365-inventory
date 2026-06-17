from django.urls import reverse

from core.factories import BaseFixtureTestCase


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
