from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import Role
from accounts.permissions import (
    has_role_at_least,
    is_admin_role,
    is_manager_or_above,
)

User = get_user_model()


class AuthUserModelTest(TestCase):
    def test_auth_user_model_setting(self):
        """3.1 AUTH_USER_MODEL 설정 테스트"""
        self.assertEqual(settings.AUTH_USER_MODEL, "accounts.User")
        self.assertEqual(User._meta.label, "accounts.User")

    def test_required_fields_empty(self):
        """3.2 REQUIRED_FIELDS 테스트"""
        self.assertEqual(User.REQUIRED_FIELDS, [])
        self.assertEqual(User.USERNAME_FIELD, "username")

    def test_create_superuser_defaults(self):
        """3.3 create_superuser 기본값 테스트"""
        admin = User.objects.create_superuser(username="admin", password="pw12345!")
        self.assertEqual(admin.role, Role.ADMIN)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_normal_user_default_role(self):
        """3.4 일반 사용자 기본 role 테스트"""
        user = User.objects.create_user(username="staff1", password="pw12345!")
        self.assertEqual(user.role, Role.STAFF)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)


class RoleHelperTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(username="s", password="x", role=Role.STAFF)
        cls.leader = User.objects.create_user(
            username="tl", password="x", role=Role.TEAM_LEADER
        )
        cls.manager = User.objects.create_user(
            username="m", password="x", role=Role.MANAGER
        )
        cls.admin = User.objects.create_user(
            username="a", password="x", role=Role.ADMIN
        )

    def test_role_ordering(self):
        """STAFF < TEAM_LEADER < MANAGER < ADMIN 순서 확인"""
        # STAFF 는 STAFF 이상만 만족
        self.assertTrue(has_role_at_least(self.staff, Role.STAFF))
        self.assertFalse(has_role_at_least(self.staff, Role.TEAM_LEADER))
        self.assertFalse(has_role_at_least(self.staff, Role.MANAGER))
        self.assertFalse(has_role_at_least(self.staff, Role.ADMIN))

        # TEAM_LEADER 는 STAFF, TEAM_LEADER 만족
        self.assertTrue(has_role_at_least(self.leader, Role.STAFF))
        self.assertTrue(has_role_at_least(self.leader, Role.TEAM_LEADER))
        self.assertFalse(has_role_at_least(self.leader, Role.MANAGER))

        # MANAGER 는 MANAGER 이하 모두 만족, ADMIN 미만
        self.assertTrue(has_role_at_least(self.manager, Role.TEAM_LEADER))
        self.assertTrue(has_role_at_least(self.manager, Role.MANAGER))
        self.assertFalse(has_role_at_least(self.manager, Role.ADMIN))

        # ADMIN 은 전부 만족
        self.assertTrue(has_role_at_least(self.admin, Role.ADMIN))

    def test_is_manager_or_above(self):
        self.assertFalse(is_manager_or_above(self.staff))
        self.assertFalse(is_manager_or_above(self.leader))
        self.assertTrue(is_manager_or_above(self.manager))
        self.assertTrue(is_manager_or_above(self.admin))

    def test_is_admin_role(self):
        self.assertFalse(is_admin_role(self.staff))
        self.assertFalse(is_admin_role(self.leader))
        self.assertFalse(is_admin_role(self.manager))
        self.assertTrue(is_admin_role(self.admin))

    def test_anonymous_or_none(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertFalse(has_role_at_least(None, Role.STAFF))
        self.assertFalse(has_role_at_least(AnonymousUser(), Role.STAFF))
