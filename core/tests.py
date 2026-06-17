from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from accounts.models import Role
from core.factories import BaseFixtureTestCase
from core.models import Department


class DepartmentModelTest(TestCase):
    def test_name_unique(self):
        """4.1 Department.name unique 테스트"""
        Department.objects.create(name="피부실")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Department.objects.create(name="피부실")

    def test_name_strip_normalization(self):
        """4.11 Department.name strip 정규화 테스트"""
        dept = Department.objects.create(name="  치료실  ")
        dept.refresh_from_db()
        self.assertEqual(dept.name, "치료실")

    def test_defaults(self):
        dept = Department.objects.create(name="데스크")
        self.assertTrue(dept.is_active)
        self.assertTrue(dept.active_for_inventory)
        self.assertEqual(dept.memo, "")


class DatabaseEngineTest(TestCase):
    def test_test_database_is_postgresql(self):
        """SQLite 테스트 방지: 테스트 DB 가 PostgreSQL 인지 확인한다. (TECH_SPEC §15)"""
        self.assertEqual(connection.vendor, "postgresql")
        self.assertIn("postgresql", connection.settings_dict["ENGINE"])


class FixtureSetupTest(BaseFixtureTestCase):
    def test_departments_created(self):
        """기본 부서 fixture 생성 확인"""
        self.assertEqual(Department.objects.count(), 3)
        self.assertTrue(self.dept_skin.active_for_inventory)
        self.assertTrue(self.dept_treatment.active_for_inventory)
        self.assertFalse(self.dept_decoction.active_for_inventory)

    def test_users_created(self):
        """기본 사용자 fixture 생성 확인"""
        self.assertEqual(self.staff_skin.role, Role.STAFF)
        self.assertEqual(self.staff_skin.department, self.dept_skin)

        self.assertEqual(self.team_leader_skin.role, Role.TEAM_LEADER)
        self.assertEqual(self.team_leader_skin.department, self.dept_skin)

        self.assertEqual(self.staff_treatment.role, Role.STAFF)
        self.assertEqual(self.staff_treatment.department, self.dept_treatment)

        self.assertEqual(self.manager.role, Role.MANAGER)
        self.assertFalse(self.manager.is_staff)
        self.assertFalse(self.manager.is_superuser)

        self.assertEqual(self.admin.role, Role.ADMIN)
        self.assertTrue(self.admin.is_staff)
        self.assertTrue(self.admin.is_superuser)
