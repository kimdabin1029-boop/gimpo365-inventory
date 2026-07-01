"""v0.2.2 상세조회 (읽기 전용) 테스트.

- 관리품목/공급업체/거래 상세조회
- 권한 범위: 상세가 목록보다 넓어지지 않는다
- 현재고 = APPROVED 합계 표시 / 주문 연결 정보 표시
"""

from decimal import Decimal

from django.urls import reverse

from core.factories import (
    BaseFixtureTestCase,
    approve_initial_count,
    create_item,
    create_managed_item,
    create_supplier,
)
from inventory.models import ItemCategory, TransactionType
from inventory.order_services import (
    add_to_cart,
    confirm_order,
    create_stock_in_from_order_item,
)
from inventory.selectors import get_current_stock
from inventory.services import create_stock_in, create_stock_out


class DetailFixture:
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.sup_a = create_supplier(name="A업체")
        cls.sup_b = create_supplier(name="B업체")
        cls.item1 = create_item("알콜솜", category=ItemCategory.HYGIENE_SUPPLY)
        cls.item2 = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi_skin = create_managed_item(
            item=cls.item1, department=cls.dept_skin, default_supplier=cls.sup_a,
            minimum_stock=5,
        )
        cls.mi_treat = create_managed_item(
            item=cls.item2, department=cls.dept_treatment, default_supplier=cls.sup_b,
        )
        approve_initial_count(cls.mi_skin, created_by=cls.manager)
        approve_initial_count(cls.mi_treat, created_by=cls.manager)


class ManagedItemDetailPermTest(DetailFixture, BaseFixtureTestCase):
    def test_staff_can_view_own_scope(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:managed_item_detail", args=[self.mi_skin.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_staff_blocked_out_of_scope(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:managed_item_detail", args=[self.mi_treat.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_team_leader_own_department(self):
        self.client.force_login(self.team_leader_skin)
        resp = self.client.get(reverse("inventory:managed_item_detail", args=[self.mi_skin.pk]))
        self.assertEqual(resp.status_code, 200)
        resp2 = self.client.get(reverse("inventory:managed_item_detail", args=[self.mi_treat.pk]))
        self.assertEqual(resp2.status_code, 404)

    def test_manager_sees_all(self):
        self.client.force_login(self.manager)
        for mi in (self.mi_skin, self.mi_treat):
            resp = self.client.get(reverse("inventory:managed_item_detail", args=[mi.pk]))
            self.assertEqual(resp.status_code, 200)

    def test_current_stock_is_approved_sum(self):
        # 입고 10, 출고 3 → 현재고 7
        create_stock_in(user=self.staff_skin, managed_item=self.mi_skin, quantity=10)
        create_stock_out(
            user=self.staff_skin, managed_item=self.mi_skin,
            transaction_type=TransactionType.OUT_USE, quantity=3,
        )
        self.assertEqual(get_current_stock(self.mi_skin), Decimal("7"))
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:managed_item_detail", args=[self.mi_skin.pk]))
        self.assertEqual(resp.context["mi"].current_stock, Decimal("7"))
        self.assertContains(resp, "APPROVED 거래 합계")


class SupplierDetailPermTest(DetailFixture, BaseFixtureTestCase):
    def test_staff_can_view_related_supplier(self):
        # sup_a 는 mi_skin(피부실)의 기본 공급업체 → 피부실 STAFF 접근 가능
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:supplier_detail", args=[self.sup_a.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_staff_blocked_unrelated_supplier(self):
        # sup_b 는 치료실 관리품목에만 연결 → 피부실 STAFF 는 접근 불가
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:supplier_detail", args=[self.sup_b.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_manager_sees_any_supplier(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:supplier_detail", args=[self.sup_b.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_supplier_lists_scoped_for_staff(self):
        # 치료실 관리품목도 sup_a 를 쓰도록 만들고 치료실 staff 가 주문
        item3 = create_item("멸균장갑", category=ItemCategory.HYGIENE_SUPPLY)
        mi_treat_a = create_managed_item(
            item=item3, department=self.dept_treatment, default_supplier=self.sup_a,
        )
        approve_initial_count(mi_treat_a, created_by=self.manager)
        add_to_cart(user=self.staff_treatment, managed_item=mi_treat_a, supplier=self.sup_a, quantity=2)
        treat_order = confirm_order(user=self.staff_treatment)[0]
        # 피부실 staff 가 sup_a 주문
        add_to_cart(user=self.staff_skin, managed_item=self.mi_skin, supplier=self.sup_a, quantity=1)
        skin_order = confirm_order(user=self.staff_skin)[0]

        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:supplier_detail", args=[self.sup_a.pk]))
        orders = list(resp.context["orders"])
        self.assertIn(skin_order, orders)
        self.assertNotIn(treat_order, orders)  # 타 부서 주문 미노출
        # 기본 공급 품목도 본인 부서 것만
        default_items = list(resp.context["default_items"])
        self.assertIn(self.mi_skin, default_items)
        self.assertNotIn(mi_treat_a, default_items)


class TransactionDetailPermTest(DetailFixture, BaseFixtureTestCase):
    def test_staff_blocked_out_of_scope_transaction(self):
        tx = create_stock_in(user=self.manager, managed_item=self.mi_treat, quantity=5)
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:transaction_detail", args=[tx.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_no_order_link_still_works(self):
        tx = create_stock_in(user=self.staff_skin, managed_item=self.mi_skin, quantity=5)
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:transaction_detail", args=[tx.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "연결된 주문 없음")

    def test_order_link_shown_when_present(self):
        add_to_cart(user=self.staff_skin, managed_item=self.mi_skin, supplier=self.sup_a, quantity=10)
        order = confirm_order(user=self.staff_skin)[0]
        oi = order.items.first()
        tx = create_stock_in_from_order_item(
            user=self.staff_skin, order_item=oi, quantity=4,
            unit_price=Decimal("1000"), no_expiration=True,
        )
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:transaction_detail", args=[tx.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, order.internal_order_no)
        self.assertContains(resp, "기입고수량")


class DetailLinkTest(DetailFixture, BaseFixtureTestCase):
    def test_stock_list_links_to_detail(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:stock_list"))
        self.assertContains(
            resp, reverse("inventory:managed_item_detail", args=[self.mi_skin.pk])
        )
        self.assertContains(
            resp, reverse("inventory:supplier_detail", args=[self.sup_a.pk])
        )
