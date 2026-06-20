from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from core.models import Department
from inventory.models import (
    Item,
    ManagedItem,
    StockTransaction,
    Supplier,
    TransactionStatus,
    TransactionType,
)
from inventory.selectors import get_current_stock

User = get_user_model()

SEED_USERNAMES = [
    "manager_test",
    "skin_staff_test",
    "skin_leader_test",
    "treatment_staff_test",
    "treatment_leader_test",
]


def _run(*args):
    out = StringIO()
    call_command("seed_alpha_inventory", *args, stdout=out)
    return out.getvalue()


class SeedAlphaInventoryTest(TestCase):
    def test_refuses_when_debug_false(self):
        """가드: DEBUG=False 면 CommandError 로 중단"""
        with override_settings(DEBUG=False):
            with self.assertRaises(CommandError):
                _run("--yes")
        self.assertEqual(Department.objects.count(), 0)
        self.assertEqual(ManagedItem.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_dry_run_creates_nothing(self):
        _run("--dry-run")
        self.assertEqual(Department.objects.count(), 0)
        self.assertEqual(Item.objects.count(), 0)
        self.assertEqual(ManagedItem.objects.count(), 0)
        self.assertEqual(User.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_default_creates_master_data(self):
        _run("--yes")
        self.assertEqual(Department.objects.count(), 3)
        self.assertEqual(Supplier.objects.count(), 3)
        self.assertEqual(User.objects.count(), 5)  # manager_test + 부서별 2명씩
        self.assertEqual(Item.objects.count(), 18)  # 공유 품목(알코올솜/장갑) 중복 제거
        self.assertEqual(ManagedItem.objects.count(), 20)  # 부서×품목 10+10

    @override_settings(DEBUG=True)
    def test_initial_count_via_service_reflected_in_stock(self):
        """초기재고가 service 계층을 통해 APPROVED 로 생성되어 현재고에 반영"""
        _run("--yes")
        skin = Department.objects.get(name="피부실")
        ample = Item.objects.get(name="[테스트] 앰플")
        mi = ManagedItem.objects.get(item=ample, department=skin)
        self.assertEqual(get_current_stock(mi), 50)
        # INITIAL_COUNT 가 APPROVED 로 존재
        self.assertTrue(
            mi.stock_transactions.filter(
                transaction_type=TransactionType.INITIAL_COUNT,
                status=TransactionStatus.APPROVED,
            ).exists()
        )

    @override_settings(DEBUG=True)
    def test_idempotent(self):
        _run("--yes")
        approved_initial = StockTransaction.objects.filter(
            transaction_type=TransactionType.INITIAL_COUNT,
            status=TransactionStatus.APPROVED,
        ).count()
        _run("--yes")  # 두 번째 실행
        self.assertEqual(Department.objects.count(), 3)
        self.assertEqual(Item.objects.count(), 18)
        self.assertEqual(ManagedItem.objects.count(), 20)
        self.assertEqual(User.objects.count(), 5)
        # 초기재고 중복 생성되지 않음
        self.assertEqual(
            StockTransaction.objects.filter(
                transaction_type=TransactionType.INITIAL_COUNT,
                status=TransactionStatus.APPROVED,
            ).count(),
            approved_initial,
        )

    @override_settings(DEBUG=True)
    def test_department_skin_only(self):
        _run("--yes", "--department", "skin")
        skin = Department.objects.get(name="피부실")
        treatment = Department.objects.get(name="치료실")
        self.assertEqual(ManagedItem.objects.filter(department=skin).count(), 10)
        self.assertEqual(ManagedItem.objects.filter(department=treatment).count(), 0)
        # 치료실 테스트 사용자 미생성
        self.assertFalse(User.objects.filter(username="treatment_staff_test").exists())
        self.assertTrue(User.objects.filter(username="skin_staff_test").exists())

    @override_settings(DEBUG=True)
    def test_department_treatment_only(self):
        _run("--yes", "--department", "treatment")
        skin = Department.objects.get(name="피부실")
        treatment = Department.objects.get(name="치료실")
        self.assertEqual(ManagedItem.objects.filter(department=treatment).count(), 10)
        self.assertEqual(ManagedItem.objects.filter(department=skin).count(), 0)
        self.assertFalse(User.objects.filter(username="skin_staff_test").exists())
        self.assertTrue(User.objects.filter(username="treatment_staff_test").exists())

    @override_settings(DEBUG=True)
    def test_usernames_compatible_with_reset_delete_test_users(self):
        """생성 username 이 reset_alpha_data --delete-test-users 패턴과 호환"""
        _run("--yes")
        for username in SEED_USERNAMES:
            self.assertTrue(
                username.startswith("test_") or username.endswith("_test"),
                username,
            )
        # 실제로 reset --delete-test-users 가 이들을 삭제하는지 확인
        call_command("reset_alpha_data", "--yes", "--delete-test-users", stdout=StringIO())
        for username in SEED_USERNAMES:
            self.assertFalse(User.objects.filter(username=username).exists())

    @override_settings(DEBUG=True)
    def test_with_transactions_idempotent(self):
        _run("--yes", "--with-transactions")
        in_count = StockTransaction.objects.filter(
            transaction_type=TransactionType.IN, memo="[seed]"
        ).count()
        self.assertGreaterEqual(in_count, 1)
        _run("--yes", "--with-transactions")
        self.assertEqual(
            StockTransaction.objects.filter(
                transaction_type=TransactionType.IN, memo="[seed]"
            ).count(),
            in_count,
        )
