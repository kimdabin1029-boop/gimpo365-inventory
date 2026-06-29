"""v0.2.0 주문 장바구니 / 주문 기록 테스트.

핵심 불변식: 주문(장바구니/주문/상태변경)은 현재고를 변경하지 않는다.
실제 재고 증가는 입고(StockTransaction IN)로만 발생한다.
"""

from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from core.factories import (
    BaseFixtureTestCase,
    approve_initial_count,
    create_item,
    create_managed_item,
    create_supplier,
)
from inventory.exceptions import OrderError, PermissionDeniedError
from inventory.models import (
    CartItem,
    ItemCategory,
    Order,
    OrderItem,
    OrderStatus,
    StockTransaction,
    TransactionType,
)
from inventory.order_selectors import get_orders, get_unreceived_orders
from inventory.order_services import (
    add_to_cart,
    cancel_order,
    confirm_order,
    generate_internal_order_no,
    get_or_create_cart,
    mark_order_received,
    remove_cart_item,
    update_cart_item,
)
from inventory.selectors import get_current_stock


class OrderFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.sup_a = create_supplier(name="A업체")
        cls.sup_b = create_supplier(name="B업체")
        cls.item1 = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.item2 = create_item("니들 30G", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi1 = create_managed_item(
            item=cls.item1, department=cls.dept_skin, default_supplier=cls.sup_a
        )
        cls.mi2 = create_managed_item(
            item=cls.item2, department=cls.dept_skin, default_supplier=cls.sup_b
        )


class CartServiceTest(OrderFixtureMixin, BaseFixtureTestCase):
    # 1. 장바구니 담기
    def test_add_to_cart(self):
        ci = add_to_cart(user=self.staff_skin, managed_item=self.mi1, quantity=2)
        self.assertEqual(ci.quantity, Decimal("2"))
        self.assertEqual(ci.supplier, self.sup_a)  # 기본 공급업체 초기값
        self.assertEqual(get_or_create_cart(self.staff_skin).items.count(), 1)

    # 2. 동일 managed_item + supplier → 수량 증가 (중복 행 X)
    def test_add_to_cart_dedupes_same_combo(self):
        add_to_cart(user=self.staff_skin, managed_item=self.mi1, supplier=self.sup_a, quantity=1)
        add_to_cart(user=self.staff_skin, managed_item=self.mi1, supplier=self.sup_a, quantity=2)
        cart = get_or_create_cart(self.staff_skin)
        self.assertEqual(cart.items.count(), 1)
        self.assertEqual(cart.items.first().quantity, Decimal("3"))

    def test_add_to_cart_different_supplier_makes_new_row(self):
        add_to_cart(user=self.staff_skin, managed_item=self.mi1, supplier=self.sup_a, quantity=1)
        add_to_cart(user=self.staff_skin, managed_item=self.mi1, supplier=self.sup_b, quantity=1)
        self.assertEqual(get_or_create_cart(self.staff_skin).items.count(), 2)

    # 3. 수량 수정 / 삭제
    def test_update_and_remove_cart_item(self):
        ci = add_to_cart(user=self.staff_skin, managed_item=self.mi1, quantity=1)
        update_cart_item(user=self.staff_skin, cart_item_id=ci.pk, quantity=5, memo="급함")
        ci.refresh_from_db()
        self.assertEqual(ci.quantity, Decimal("5"))
        self.assertEqual(ci.memo, "급함")
        remove_cart_item(user=self.staff_skin, cart_item_id=ci.pk)
        self.assertFalse(CartItem.objects.filter(pk=ci.pk).exists())

    def test_cannot_touch_other_users_cart_item(self):
        ci = add_to_cart(user=self.staff_skin, managed_item=self.mi1, quantity=1)
        with self.assertRaises(OrderError):
            remove_cart_item(user=self.team_leader_skin, cart_item_id=ci.pk)

    def test_add_to_cart_other_department_denied(self):
        mi_treat = create_managed_item(item=self.item1, department=self.dept_treatment)
        with self.assertRaises(PermissionDeniedError):
            add_to_cart(user=self.staff_skin, managed_item=mi_treat, quantity=1)


class OrderConfirmTest(OrderFixtureMixin, BaseFixtureTestCase):
    # 4. 공급업체별 Order 생성
    def test_confirm_splits_by_supplier(self):
        add_to_cart(user=self.staff_skin, managed_item=self.mi1, supplier=self.sup_a, quantity=2)
        add_to_cart(user=self.staff_skin, managed_item=self.mi2, supplier=self.sup_b, quantity=1)
        orders = confirm_order(user=self.staff_skin)
        self.assertEqual(len(orders), 2)
        suppliers = {o.supplier for o in orders}
        self.assertEqual(suppliers, {self.sup_a, self.sup_b})
        # 각 주문은 단일 공급업체 + 해당 품목
        for o in orders:
            self.assertEqual(o.status, OrderStatus.ORDERED)
            self.assertEqual(o.items.count(), 1)
        # 장바구니 비워짐
        self.assertEqual(get_or_create_cart(self.staff_skin).items.count(), 0)

    # 5. 내부 주문번호 YYMMDD-순번
    def test_internal_order_no_format_and_sequence(self):
        today = timezone.localdate().strftime("%y%m%d")
        add_to_cart(user=self.staff_skin, managed_item=self.mi1, supplier=self.sup_a, quantity=1)
        o1 = confirm_order(user=self.staff_skin)[0]
        self.assertEqual(o1.internal_order_no, f"{today}-1")
        add_to_cart(user=self.staff_skin, managed_item=self.mi1, supplier=self.sup_a, quantity=1)
        o2 = confirm_order(user=self.staff_skin)[0]
        self.assertEqual(o2.internal_order_no, f"{today}-2")

    def test_generate_internal_order_no_helper(self):
        today = timezone.localdate().strftime("%y%m%d")
        self.assertEqual(generate_internal_order_no(), f"{today}-1")

    # 6. 외부 주문번호 없이 주문 가능
    def test_confirm_without_external_order_no(self):
        add_to_cart(user=self.staff_skin, managed_item=self.mi1, supplier=self.sup_a, quantity=1)
        orders = confirm_order(user=self.staff_skin)
        self.assertEqual(orders[0].external_order_no, "")

    def test_confirm_with_external_order_no(self):
        add_to_cart(user=self.staff_skin, managed_item=self.mi1, supplier=self.sup_a, quantity=1)
        orders = confirm_order(user=self.staff_skin, external_order_no="SHOP-999")
        self.assertEqual(orders[0].external_order_no, "SHOP-999")

    def test_confirm_empty_cart_raises(self):
        with self.assertRaises(OrderError):
            confirm_order(user=self.staff_skin)

    def test_confirm_missing_supplier_raises(self):
        # 기본 공급업체 없는 품목 → supplier 미지정으로 담기면 확정 차단
        mi_no_sup = create_managed_item(item=create_item("멸균거즈"), department=self.dept_skin)
        add_to_cart(user=self.staff_skin, managed_item=mi_no_sup, quantity=1)
        with self.assertRaises(OrderError):
            confirm_order(user=self.staff_skin)

    # 7. 주문 생성은 현재고를 바꾸지 않는다
    def test_confirm_does_not_change_stock(self):
        approve_initial_count(self.mi1, created_by=self.manager, quantity=10)
        self.assertEqual(get_current_stock(self.mi1), Decimal("10"))
        add_to_cart(user=self.staff_skin, managed_item=self.mi1, supplier=self.sup_a, quantity=5)
        confirm_order(user=self.staff_skin)
        self.assertEqual(get_current_stock(self.mi1), Decimal("10"))
        # 입고(IN) 거래는 생성되지 않음
        self.assertFalse(
            StockTransaction.objects.filter(
                managed_item=self.mi1, transaction_type=TransactionType.IN
            ).exists()
        )


class OrderStatusTest(OrderFixtureMixin, BaseFixtureTestCase):
    def _make_order(self, *, user=None):
        user = user or self.staff_skin
        add_to_cart(user=user, managed_item=self.mi1, supplier=self.sup_a, quantity=1)
        return confirm_order(user=user)[0]

    # 9. ORDERED 취소 가능
    def test_cancel_ordered(self):
        order = self._make_order()
        cancel_order(user=self.staff_skin, order=order, reason="중복주문")
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CANCELED)
        self.assertEqual(order.canceled_by, self.staff_skin)
        self.assertIsNotNone(order.canceled_at)
        self.assertIn("중복주문", order.memo)

    # 10. 취소는 현재고에 영향 없음
    def test_cancel_does_not_change_stock(self):
        approve_initial_count(self.mi1, created_by=self.manager, quantity=8)
        order = self._make_order()
        cancel_order(user=self.staff_skin, order=order, reason="x")
        self.assertEqual(get_current_stock(self.mi1), Decimal("8"))

    # 11. RECEIVED 는 취소 불가
    def test_received_cannot_be_canceled(self):
        order = self._make_order()
        mark_order_received(user=self.manager, order=order)
        with self.assertRaises(OrderError):
            cancel_order(user=self.manager, order=order, reason="x")

    # 12. RECEIVED 처리해도 현재고 증가 없음
    def test_mark_received_does_not_change_stock(self):
        approve_initial_count(self.mi1, created_by=self.manager, quantity=4)
        order = self._make_order()
        mark_order_received(user=self.manager, order=order)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.RECEIVED)
        self.assertEqual(order.received_by, self.manager)
        self.assertEqual(get_current_stock(self.mi1), Decimal("4"))
        self.assertFalse(
            StockTransaction.objects.filter(
                managed_item=self.mi1, transaction_type=TransactionType.IN
            ).exists()
        )

    # 권한: 타인(주문자 아님, 비매니저)은 취소/입고완료 불가
    def test_other_staff_cannot_cancel(self):
        # 같은 부서의 다른 STAFF 가 주문 → 본인 주문 아님
        order = self._make_order(user=self.team_leader_skin)
        with self.assertRaises(PermissionDeniedError):
            cancel_order(user=self.staff_skin, order=order, reason="x")

    def test_owner_can_cancel(self):
        order = self._make_order(user=self.staff_skin)
        cancel_order(user=self.staff_skin, order=order, reason="x")
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CANCELED)


class OrderSelectorPermissionTest(OrderFixtureMixin, BaseFixtureTestCase):
    def _order_as(self, user, mi, supplier):
        add_to_cart(user=user, managed_item=mi, supplier=supplier, quantity=1)
        return confirm_order(user=user)[0]

    def test_manager_sees_all_orders(self):
        self._order_as(self.staff_skin, self.mi1, self.sup_a)
        self.assertEqual(get_orders(self.manager).count(), 1)

    def test_staff_sees_own_department_orders(self):
        # 피부실 팀장 주문 → 피부실 STAFF 도 본인 부서 주문으로 조회 가능
        self._order_as(self.team_leader_skin, self.mi1, self.sup_a)
        self.assertEqual(get_orders(self.staff_skin).count(), 1)

    def test_staff_does_not_see_other_department_orders(self):
        # 치료실 STAFF 가 치료실 품목 주문
        mi_treat = create_managed_item(
            item=self.item1, department=self.dept_treatment, default_supplier=self.sup_a
        )
        self._order_as(self.staff_treatment, mi_treat, self.sup_a)
        # 피부실 STAFF 에게는 보이지 않음
        self.assertEqual(get_orders(self.staff_skin).count(), 0)


class OrderViewTest(OrderFixtureMixin, BaseFixtureTestCase):
    def _make_order(self, user=None):
        user = user or self.staff_skin
        add_to_cart(user=user, managed_item=self.mi1, supplier=self.sup_a, quantity=2)
        return confirm_order(user=user)[0]

    # 1(view). 장바구니 담기 (POST)
    def test_add_to_cart_view(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.post(
            reverse("inventory:cart_add"),
            data={"managed_item": self.mi1.pk, "supplier": self.sup_a.pk, "quantity": "3"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(get_or_create_cart(self.staff_skin).items.first().quantity, Decimal("3"))

    # 8. 주문 목록/상세 표시
    def test_order_list_and_detail(self):
        order = self._make_order()
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:order_list"))
        self.assertContains(resp, order.internal_order_no)
        resp2 = self.client.get(reverse("inventory:order_detail", args=[order.pk]))
        self.assertContains(resp2, self.item1.name)
        self.assertContains(resp2, self.sup_a.name)

    def test_order_detail_permission_404_for_other_department(self):
        mi_treat = create_managed_item(
            item=self.item1, department=self.dept_treatment, default_supplier=self.sup_a
        )
        add_to_cart(user=self.staff_treatment, managed_item=mi_treat, supplier=self.sup_a, quantity=1)
        order = confirm_order(user=self.staff_treatment)[0]
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:order_detail", args=[order.pk]))
        self.assertEqual(resp.status_code, 404)

    # 13. 대시보드 미입고(ORDERED) 주문 표시
    def test_dashboard_shows_unreceived(self):
        order = self._make_order()
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:dashboard"))
        self.assertContains(resp, order.internal_order_no)
        self.assertContains(resp, "미입고 주문")

    # 14. 좌측 퀵메뉴에 주문 메뉴
    def test_sidebar_has_order_menu(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:dashboard"))
        self.assertContains(resp, reverse("inventory:cart"))
        self.assertContains(resp, reverse("inventory:order_list"))

    def test_confirm_view_creates_orders(self):
        add_to_cart(user=self.staff_skin, managed_item=self.mi1, supplier=self.sup_a, quantity=1)
        add_to_cart(user=self.staff_skin, managed_item=self.mi2, supplier=self.sup_b, quantity=1)
        self.client.force_login(self.staff_skin)
        resp = self.client.post(
            reverse("inventory:order_confirm"),
            data={"order_date": timezone.localdate().strftime("%Y-%m-%d"),
                  "external_order_no": "", "memo": ""},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Order.objects.count(), 2)
        self.assertEqual(OrderItem.objects.count(), 2)

    # 입고 등록 prefill: 주문 상세의 "입고 등록으로 이동" 링크가 품목/공급업체를 넘긴다
    def test_stock_in_prefill_from_order(self):
        order = self._make_order()
        self.client.force_login(self.staff_skin)
        resp = self.client.get(
            reverse("inventory:stock_in_new")
            + f"?managed_item={self.mi1.pk}&supplier={self.sup_a.pk}"
        )
        self.assertEqual(resp.status_code, 200)
        form = resp.context["form"]
        self.assertEqual(str(form["managed_item"].value()), str(self.mi1.pk))
        self.assertEqual(str(form["supplier"].value()), str(self.sup_a.pk))
