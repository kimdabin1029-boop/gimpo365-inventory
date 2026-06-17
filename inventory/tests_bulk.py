from decimal import Decimal

from core.factories import BaseFixtureTestCase, create_item, create_managed_item
from inventory.exceptions import PermissionDeniedError
from inventory.models import ItemCategory, TransactionStatus, TransactionType
from inventory.selectors import get_current_stock
from inventory.services import (
    approve_transaction,
    bulk_approve_initial_counts,
    create_stock_in,
    request_adjustment,
    request_initial_count,
)


class BulkApproveInitialCountsTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item_a = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.item_b = create_item("니들 30G", category=ItemCategory.MEDICAL_SUPPLY)
        cls.item_c = create_item("알콜솜", category=ItemCategory.HYGIENE_SUPPLY)
        cls.mi_a = create_managed_item(item=cls.item_a, department=cls.dept_skin)
        cls.mi_b = create_managed_item(item=cls.item_b, department=cls.dept_skin)
        cls.mi_c = create_managed_item(item=cls.item_c, department=cls.dept_skin)

    def _pending_initial(self, mi, qty=10):
        return request_initial_count(
            user=self.staff_skin, managed_item=mi, quantity=qty
        )

    def test_bulk_approve_success(self):
        """13.1 초기재고 일괄 승인 성공 테스트"""
        t1 = self._pending_initial(self.mi_a, 10)
        t2 = self._pending_initial(self.mi_b, 20)
        t3 = self._pending_initial(self.mi_c, 30)
        result = bulk_approve_initial_counts(
            user=self.manager, transaction_ids=[t1.pk, t2.pk, t3.pk]
        )
        self.assertEqual(len(result["approved"]), 3)
        self.assertEqual(len(result["skipped"]), 0)
        self.assertEqual(get_current_stock(self.mi_a), Decimal("10"))
        self.assertEqual(get_current_stock(self.mi_b), Decimal("20"))
        self.assertEqual(get_current_stock(self.mi_c), Decimal("30"))

    def test_bulk_partial_success(self):
        """13.2 일부 실패 부분 성공 테스트

        같은 ManagedItem(mi_a)에 PENDING 초기재고 2건 → 첫 건 승인, 둘째 건은
        '이미 승인된 초기재고가 있음'으로 skip. mi_b 는 정상 승인.
        """
        a1 = self._pending_initial(self.mi_a, 10)
        a2 = self._pending_initial(self.mi_a, 12)  # PENDING 중복 허용
        b1 = self._pending_initial(self.mi_b, 20)
        result = bulk_approve_initial_counts(
            user=self.manager, transaction_ids=[a1.pk, a2.pk, b1.pk]
        )
        self.assertIn(a1.pk, result["approved"])
        self.assertIn(b1.pk, result["approved"])
        skipped_ids = [s["id"] for s in result["skipped"]]
        self.assertIn(a2.pk, skipped_ids)
        self.assertEqual(len(result["approved"]), 2)
        self.assertEqual(len(result["skipped"]), 1)

    def test_one_failure_does_not_rollback_others(self):
        """13.3 한 건 실패가 전체 롤백하지 않는지 테스트"""
        a1 = self._pending_initial(self.mi_a, 10)
        a2 = self._pending_initial(self.mi_a, 12)  # 둘째는 skip 될 것
        b1 = self._pending_initial(self.mi_b, 20)
        bulk_approve_initial_counts(
            user=self.manager, transaction_ids=[a1.pk, a2.pk, b1.pk]
        )
        a1.refresh_from_db()
        a2.refresh_from_db()
        b1.refresh_from_db()
        # 성공 건은 실제로 APPROVED 로 저장되어 있어야 한다 (롤백되지 않음)
        self.assertEqual(a1.status, TransactionStatus.APPROVED)
        self.assertEqual(b1.status, TransactionStatus.APPROVED)
        # skip 건은 여전히 PENDING
        self.assertEqual(a2.status, TransactionStatus.PENDING)

    def test_bulk_approve_permission(self):
        """13.4 bulk approve 권한 테스트"""
        t1 = self._pending_initial(self.mi_a, 10)
        with self.assertRaises(PermissionDeniedError):
            bulk_approve_initial_counts(
                user=self.staff_skin, transaction_ids=[t1.pk]
            )

    def test_adjustment_excluded_from_bulk(self):
        """13.5 ADJUSTMENT는 bulk approve 대상 제외"""
        create_stock_in(user=self.manager, managed_item=self.mi_a, quantity=10)
        adj = request_adjustment(
            user=self.staff_skin,
            managed_item=self.mi_a,
            actual_quantity=7,
            reason="실사",
        )
        result = bulk_approve_initial_counts(
            user=self.manager, transaction_ids=[adj.pk]
        )
        self.assertEqual(len(result["approved"]), 0)
        self.assertEqual(len(result["skipped"]), 1)
        adj.refresh_from_db()
        self.assertEqual(adj.status, TransactionStatus.PENDING)
