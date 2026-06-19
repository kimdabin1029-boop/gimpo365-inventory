from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from accounts.models import Role
from core.factories import (
    BaseFixtureTestCase,
    create_item,
    create_managed_item,
    create_stock_transaction,
    create_supplier,
)
from inventory.models import (
    Item,
    ItemCategory,
    ManagedItem,
    StockTransaction,
    Supplier,
    TransactionStatus,
    TransactionType,
)

User = get_user_model()


class ResetAlphaDataTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.supplier = create_supplier(name="메디칼코리아")
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(
            item=cls.item, department=cls.dept_skin, default_supplier=cls.supplier
        )
        create_stock_transaction(
            managed_item=cls.mi,
            transaction_type=TransactionType.IN,
            created_by=cls.staff_skin,
            status=TransactionStatus.APPROVED,
            quantity_input=10,
            quantity_delta=10,
        )

    def _run(self, *args):
        out = StringIO()
        call_command("reset_alpha_data", *args, stdout=out)
        return out.getvalue()

    def test_refuses_when_debug_false(self):
        """가드: DEBUG=False 면 CommandError 로 중단 (운영 보호)"""
        with override_settings(DEBUG=False):
            with self.assertRaises(CommandError):
                self._run("--yes")
        # 아무것도 삭제되지 않음
        self.assertEqual(StockTransaction.objects.count(), 1)

    @override_settings(DEBUG=True)
    def test_dry_run_deletes_nothing(self):
        """--dry-run: 실제 삭제 없음"""
        self._run("--dry-run")
        self.assertEqual(StockTransaction.objects.count(), 1)
        self.assertEqual(ManagedItem.objects.count(), 1)
        self.assertEqual(Item.objects.count(), 1)
        self.assertEqual(Supplier.objects.count(), 1)

    @override_settings(DEBUG=True)
    def test_default_reset_keeps_users_and_departments(self):
        """기본 reset: 재고 데이터만 삭제, 사용자/부서 유지"""
        dept_count = self.dept_skin.__class__.objects.count()
        user_count = User.objects.count()

        self._run("--yes")

        self.assertEqual(StockTransaction.objects.count(), 0)
        self.assertEqual(ManagedItem.objects.count(), 0)
        self.assertEqual(Item.objects.count(), 0)
        self.assertEqual(Supplier.objects.count(), 0)
        # 부서/사용자 유지
        self.assertEqual(self.dept_skin.__class__.objects.count(), dept_count)
        self.assertEqual(User.objects.count(), user_count)
        # superuser(admin) 유지
        self.assertTrue(User.objects.filter(username="admin", is_superuser=True).exists())

    @override_settings(DEBUG=True)
    def test_delete_test_users_only_targets_test_accounts(self):
        """--delete-test-users: test_/_test 계정만 삭제, superuser/ADMIN 보호"""
        User.objects.create_user(username="test_temp", password="x")
        User.objects.create_user(username="qa_test", password="x")
        # test_ 접두지만 ADMIN 역할 → 삭제 대상 아님
        User.objects.create_user(username="test_admin", password="x", role=Role.ADMIN)
        keep_normal = self.staff_skin.username  # 일반 계정 유지

        self._run("--yes", "--delete-test-users")

        self.assertFalse(User.objects.filter(username="test_temp").exists())
        self.assertFalse(User.objects.filter(username="qa_test").exists())
        # ADMIN 역할 test_ 계정은 보존
        self.assertTrue(User.objects.filter(username="test_admin").exists())
        # 일반 계정/superuser 보존
        self.assertTrue(User.objects.filter(username=keep_normal).exists())
        self.assertTrue(User.objects.filter(username="admin", is_superuser=True).exists())

    @override_settings(DEBUG=True)
    def test_default_does_not_delete_users(self):
        """기본 동작은 사용자 삭제 안 함 (--delete-test-users 미사용)"""
        User.objects.create_user(username="test_temp", password="x")
        self._run("--yes")
        self.assertTrue(User.objects.filter(username="test_temp").exists())
