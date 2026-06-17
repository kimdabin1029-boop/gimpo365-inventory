from django.contrib.auth import get_user_model
from django.urls import reverse

from core.factories import BaseFixtureTestCase

User = get_user_model()


class PasswordChangeFlowTest(BaseFixtureTestCase):
    def test_password_change_page_requires_login(self):
        resp = self.client.get(reverse("accounts:password_change"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:login"), resp.url)

    def test_password_change_page_renders(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("accounts:password_change"))
        self.assertEqual(resp.status_code, 200)

    def test_employee_can_change_own_password(self):
        # 알려진 비밀번호로 staff 계정 준비
        user = User.objects.create_user(username="emp1", password="oldpass123!")
        self.assertTrue(self.client.login(username="emp1", password="oldpass123!"))
        resp = self.client.post(
            reverse("accounts:password_change"),
            data={
                "old_password": "oldpass123!",
                "new_password1": "newpass456!",
                "new_password2": "newpass456!",
            },
        )
        self.assertEqual(resp.status_code, 302)  # done 으로 redirect
        # 새 비밀번호로 로그인 가능, 기존 비밀번호는 불가
        self.client.logout()
        self.assertFalse(self.client.login(username="emp1", password="oldpass123!"))
        self.assertTrue(self.client.login(username="emp1", password="newpass456!"))


class AccountPolicyTest(BaseFixtureTestCase):
    def test_inactive_user_cannot_login(self):
        User.objects.create_user(
            username="left", password="pw12345!", is_active=False
        )
        self.assertFalse(self.client.login(username="left", password="pw12345!"))

    def test_active_user_can_login(self):
        User.objects.create_user(username="active1", password="pw12345!")
        self.assertTrue(self.client.login(username="active1", password="pw12345!"))


class UserAdminAddFormTest(BaseFixtureTestCase):
    def test_admin_user_add_page_has_password_fields(self):
        """1/9. UserAdmin 추가 화면에 비밀번호 입력/확인 필드가 있다."""
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin:accounts_user_add"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "password1")
        self.assertContains(resp, "password2")

    def test_navbar_has_password_change_link(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:dashboard"))
        self.assertContains(resp, reverse("accounts:password_change"))
