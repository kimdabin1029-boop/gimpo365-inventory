"""v0.1.2 알파 피드백 핫픽스 테스트.

- 거래 상세(메모 포함) + 접근 권한 범위 유지
- 입고 공급업체 초기값(기본 공급업체) + 등록 공급업체만 선택 가능
- reset_training_transactions (DEBUG 전용, dry-run 기본, StockTransaction 만 삭제)
"""

from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from core.factories import (
    BaseFixtureTestCase,
    approve_initial_count,
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
from inventory.services import create_stock_in

User = get_user_model()


class TransactionDetailViewTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi_skin = create_managed_item(item=cls.item, department=cls.dept_skin)
        cls.mi_treat = create_managed_item(item=cls.item, department=cls.dept_treatment)
        approve_initial_count(cls.mi_skin, created_by=cls.manager)
        approve_initial_count(cls.mi_treat, created_by=cls.manager)
        cls.tx_skin = create_stock_in(
            user=cls.staff_skin, managed_item=cls.mi_skin, quantity=10,
            memo="로트번호 A-123 확인",
        )
        cls.tx_treat = create_stock_in(
            user=cls.manager, managed_item=cls.mi_treat, quantity=5, memo="치료실 입고",
        )

    # 1. 거래이력 → 상세 화면 이동 가능
    def test_list_has_detail_link(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:transaction_list"))
        self.assertContains(
            resp, reverse("inventory:transaction_detail", args=[self.tx_skin.pk])
        )

    def test_detail_page_renders(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(
            reverse("inventory:transaction_detail", args=[self.tx_skin.pk])
        )
        self.assertEqual(resp.status_code, 200)

    # 2. 상세에서 메모 확인 가능
    def test_detail_shows_memo(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(
            reverse("inventory:transaction_detail", args=[self.tx_skin.pk])
        )
        self.assertContains(resp, "로트번호 A-123 확인")

    def test_detail_memo_empty_shows_placeholder(self):
        tx = create_stock_in(
            user=self.staff_skin, managed_item=self.mi_skin, quantity=3, memo="",
        )
        self.client.force_login(self.staff_skin)
        resp = self.client.get(
            reverse("inventory:transaction_detail", args=[tx.pk])
        )
        self.assertContains(resp, "메모 없음")

    # 3. 상세 접근 권한이 거래이력 접근 권한보다 넓어지지 않음
    def test_staff_cannot_view_other_department_detail(self):
        """STAFF(피부실)는 치료실 거래 상세에 접근 불가 (404)."""
        self.client.force_login(self.staff_skin)
        resp = self.client.get(
            reverse("inventory:transaction_detail", args=[self.tx_treat.pk])
        )
        self.assertEqual(resp.status_code, 404)

    def test_manager_can_view_any_detail(self):
        self.client.force_login(self.manager)
        resp = self.client.get(
            reverse("inventory:transaction_detail", args=[self.tx_skin.pk])
        )
        self.assertEqual(resp.status_code, 200)

    def test_detail_requires_login(self):
        resp = self.client.get(
            reverse("inventory:transaction_detail", args=[self.tx_skin.pk])
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:login"), resp.url)


class StockInSupplierUXTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.supplier_default = create_supplier(name="메디칼코리아")
        cls.supplier_other = create_supplier(name="대체상사")
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(
            item=cls.item, department=cls.dept_skin,
            default_supplier=cls.supplier_default,
        )
        approve_initial_count(cls.mi, created_by=cls.manager)

    # 4. 기본 공급업체가 초기값으로 표시 (옵션에 data-supplier 부여)
    def test_default_supplier_presented_as_initial(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:stock_in_new"))
        # 선택 품목 옵션에 기본 공급업체 pk 가 실려 입고 화면에서 초기값으로 자동 선택된다.
        self.assertContains(resp, f'data-supplier="{self.supplier_default.pk}"')

    # 5. 다른 등록 공급업체로 변경 가능
    def test_can_register_with_other_supplier(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.post(
            reverse("inventory:stock_in_new"),
            data={
                "managed_item": self.mi.pk,
                "quantity": "5",
                "occurred_at": timezone.localdate().strftime("%Y-%m-%d"),
                "supplier": self.supplier_other.pk,
            },
        )
        self.assertEqual(resp.status_code, 200)
        tx = StockTransaction.objects.get(
            managed_item=self.mi, transaction_type=TransactionType.IN
        )
        self.assertEqual(tx.supplier, self.supplier_other)

    # 6. 등록되지 않은 공급업체는 자유 텍스트로 저장 불가
    def test_unregistered_supplier_rejected(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.post(
            reverse("inventory:stock_in_new"),
            data={
                "managed_item": self.mi.pk,
                "quantity": "5",
                "occurred_at": timezone.localdate().strftime("%Y-%m-%d"),
                "supplier": "없는공급업체이름",  # 자유 텍스트 → ModelChoiceField 거부
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(
            StockTransaction.objects.filter(
                managed_item=self.mi, transaction_type=TransactionType.IN
            ).exists()
        )

    def test_nonexistent_supplier_pk_rejected(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.post(
            reverse("inventory:stock_in_new"),
            data={
                "managed_item": self.mi.pk,
                "quantity": "5",
                "occurred_at": timezone.localdate().strftime("%Y-%m-%d"),
                "supplier": "999999",  # 등록되지 않은 pk
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(
            StockTransaction.objects.filter(
                managed_item=self.mi, transaction_type=TransactionType.IN
            ).exists()
        )


class ResetTrainingTransactionsTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.supplier = create_supplier(name="메디칼코리아")
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(
            item=cls.item, department=cls.dept_skin, default_supplier=cls.supplier
        )

        def tx(ttype, status, days_ago):
            return create_stock_transaction(
                managed_item=cls.mi,
                transaction_type=ttype,
                created_by=cls.staff_skin,
                status=status,
                quantity_input=1,
                quantity_delta=1,
                occurred_at=timezone.now() - timedelta(days=days_ago),
            )

        # 거래유형/상태/거래일자가 다양한 거래기록
        tx(TransactionType.INITIAL_COUNT, TransactionStatus.APPROVED, 10)
        tx(TransactionType.IN, TransactionStatus.APPROVED, 5)
        tx(TransactionType.OUT_USE, TransactionStatus.APPROVED, 2)
        tx(TransactionType.ADJUSTMENT, TransactionStatus.PENDING, 1)

    def _run(self, *args):
        out = StringIO()
        call_command("reset_training_transactions", *args, stdout=out)
        return out.getvalue()

    # 10. DEBUG=False 에서는 실행 차단
    def test_refuses_when_debug_false(self):
        with override_settings(DEBUG=False):
            with self.assertRaises(CommandError):
                self._run("--yes")
        self.assertEqual(StockTransaction.objects.count(), 4)

    # 7. dry-run 에서는 삭제되지 않음
    @override_settings(DEBUG=True)
    def test_dry_run_deletes_nothing(self):
        out = self._run()  # 기본 dry-run
        self.assertEqual(StockTransaction.objects.count(), 4)
        self.assertIn("dry-run", out)

    # 8 & 9. --yes 시 StockTransaction 만 삭제, 마스터/조직 데이터 유지
    @override_settings(DEBUG=True)
    def test_yes_deletes_only_transactions(self):
        supplier_count = Supplier.objects.count()
        item_count = Item.objects.count()
        mi_count = ManagedItem.objects.count()
        dept_count = self.dept_skin.__class__.objects.count()
        user_count = User.objects.count()

        self._run("--yes")

        self.assertEqual(StockTransaction.objects.count(), 0)
        self.assertEqual(Supplier.objects.count(), supplier_count)
        self.assertEqual(Item.objects.count(), item_count)
        self.assertEqual(ManagedItem.objects.count(), mi_count)
        self.assertEqual(self.dept_skin.__class__.objects.count(), dept_count)
        self.assertEqual(User.objects.count(), user_count)

    @override_settings(DEBUG=True)
    def test_type_and_status_breakdown_in_output(self):
        out = self._run()
        # 거래유형별
        self.assertIn("INITIAL_COUNT", out)
        self.assertIn("IN", out)
        self.assertIn("OUT", out)
        self.assertIn("ADJUSTMENT", out)
        # 상태별
        self.assertIn("PENDING", out)
        self.assertIn("APPROVED", out)
        self.assertIn("REJECTED", out)
        self.assertIn("CANCELED", out)

    @override_settings(DEBUG=True)
    def test_date_filter_limits_deletion(self):
        # 최근 3일 이내(거래일자) 만 삭제 → OUT_USE(2일), ADJUSTMENT(1일) 2건
        date_from = (timezone.localdate() - timedelta(days=3)).strftime("%Y-%m-%d")
        self._run("--yes", "--from", date_from)
        self.assertEqual(StockTransaction.objects.count(), 2)
        # 남은 것은 INITIAL_COUNT, IN
        remaining = set(
            StockTransaction.objects.values_list("transaction_type", flat=True)
        )
        self.assertEqual(
            remaining, {TransactionType.INITIAL_COUNT, TransactionType.IN}
        )
