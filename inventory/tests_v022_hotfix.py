"""v0.2.2-hotfix 테스트: 장바구니 선택 주문 / 숫자 콤마 / 미입고 잔여마감.

원칙 유지: 주문/주문상태 변경·잔여마감은 현재고를 바꾸지 않는다.
현재고 = APPROVED StockTransaction.quantity_delta 합계.
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
    RemainingCloseReason,
    StockTransaction,
)
from inventory.order_selectors import (
    get_pending_order_items,
    remaining_quantity,
)
from inventory.order_services import (
    add_to_cart,
    close_remaining,
    confirm_order,
    create_stock_in_from_order_item,
    get_or_create_cart,
)
from inventory.selectors import get_current_stock


class CartFixture:
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.sup_a = create_supplier(name="A업체")
        cls.sup_b = create_supplier(name="B업체")
        cls.i1 = create_item("알콜솜", category=ItemCategory.HYGIENE_SUPPLY)
        cls.i2 = create_item("거즈", category=ItemCategory.MEDICAL_SUPPLY)
        cls.i3 = create_item("니들", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi1 = create_managed_item(item=cls.i1, department=cls.dept_skin, default_supplier=cls.sup_a)
        cls.mi2 = create_managed_item(item=cls.i2, department=cls.dept_skin, default_supplier=cls.sup_a)
        cls.mi3 = create_managed_item(item=cls.i3, department=cls.dept_skin, default_supplier=cls.sup_b)
        for mi in (cls.mi1, cls.mi2, cls.mi3):
            approve_initial_count(mi, created_by=cls.manager)


class CartSelectiveOrderServiceTest(CartFixture, BaseFixtureTestCase):
    def _fill_cart(self):
        a = add_to_cart(user=self.staff_skin, managed_item=self.mi1, supplier=self.sup_a, quantity=1)
        b = add_to_cart(user=self.staff_skin, managed_item=self.mi2, supplier=self.sup_a, quantity=2)
        c = add_to_cart(user=self.staff_skin, managed_item=self.mi3, supplier=self.sup_b, quantity=3)
        return a, b, c

    def test_selected_items_only_are_ordered(self):
        a, b, c = self._fill_cart()
        orders = confirm_order(user=self.staff_skin, cart_item_ids=[a.pk, b.pk])
        # a,b 는 같은 공급업체(A) → Order 1건, OrderItem 2건
        self.assertEqual(len(orders), 1)
        self.assertEqual(OrderItem.objects.count(), 2)
        # 선택 안 한 c 는 장바구니에 남는다
        remaining = list(get_or_create_cart(self.staff_skin).items.all())
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].pk, c.pk)

    def test_empty_selection_blocked(self):
        self._fill_cart()
        with self.assertRaises(OrderError):
            confirm_order(user=self.staff_skin, cart_item_ids=[])

    def test_full_order_still_works(self):
        self._fill_cart()
        orders = confirm_order(user=self.staff_skin)  # 전체
        # A업체(mi1,mi2) 1건 + B업체(mi3) 1건 = 2건
        self.assertEqual(len(orders), 2)
        self.assertEqual(get_or_create_cart(self.staff_skin).items.count(), 0)

    def test_selective_does_not_change_stock(self):
        a, b, c = self._fill_cart()
        confirm_order(user=self.staff_skin, cart_item_ids=[a.pk])
        self.assertEqual(get_current_stock(self.mi1), Decimal("0"))


class CartSelectiveOrderViewTest(CartFixture, BaseFixtureTestCase):
    def test_selected_flow_via_views(self):
        a = add_to_cart(user=self.staff_skin, managed_item=self.mi1, supplier=self.sup_a, quantity=1)
        b = add_to_cart(user=self.staff_skin, managed_item=self.mi2, supplier=self.sup_a, quantity=2)
        c = add_to_cart(user=self.staff_skin, managed_item=self.mi3, supplier=self.sup_b, quantity=3)
        self.client.force_login(self.staff_skin)
        # 확정 화면: 선택 2건
        resp = self.client.get(
            reverse("inventory:order_confirm"),
            {"mode": "selected", "cart_items": [a.pk, b.pk]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["items"]), 2)
        # 확정 POST
        resp2 = self.client.post(
            reverse("inventory:order_confirm"),
            {
                "mode": "selected", "cart_items": [a.pk, b.pk],
                "order_date": timezone.localdate().strftime("%Y-%m-%d"),
                "external_order_no": "", "memo": "",
            },
        )
        self.assertEqual(resp2.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)
        # c 만 장바구니에 남음
        self.assertEqual(CartItem.objects.filter(cart__user=self.staff_skin).count(), 1)

    def test_cart_page_has_selection_ui(self):
        add_to_cart(user=self.staff_skin, managed_item=self.mi1, supplier=self.sup_a, quantity=1)
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:cart"))
        self.assertContains(resp, 'name="cart_items"')
        self.assertContains(resp, "선택 항목 주문하기")
        self.assertContains(resp, "전체 항목 주문하기")


class NumberCommaTemplateTest(CartFixture, BaseFixtureTestCase):
    def test_stock_list_shows_comma_and_input_has_no_comma(self):
        # 현재고 1000 만들기: 초기재고 이미 0 승인됨 → 입고 1000
        from inventory.services import create_stock_in
        create_stock_in(user=self.staff_skin, managed_item=self.mi1, quantity=1000)
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:stock_list"))
        self.assertContains(resp, "1,000")

    def test_cart_input_value_has_no_comma(self):
        add_to_cart(user=self.staff_skin, managed_item=self.mi1, supplier=self.sup_a, quantity=1000)
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:cart"))
        html = resp.content.decode()
        self.assertIn('value="1000"', html)      # input 은 콤마 없음
        self.assertNotIn('value="1,000"', html)


class RemainingCloseTest(CartFixture, BaseFixtureTestCase):
    def _order_with_partial_receipt(self, order_qty=10, receive=6):
        add_to_cart(user=self.staff_skin, managed_item=self.mi1, supplier=self.sup_a, quantity=order_qty)
        order = confirm_order(user=self.staff_skin)[0]
        oi = order.items.first()
        if receive:
            create_stock_in_from_order_item(
                user=self.staff_skin, order_item=oi, quantity=receive,
                unit_price=Decimal("1000"), no_expiration=True,
            )
        return order, oi

    def test_unprocessed_remaining_after_partial(self):
        order, oi = self._order_with_partial_receipt(10, 6)
        self.assertEqual(remaining_quantity(oi), Decimal("4"))

    def test_close_removes_from_pending_and_no_stock_change(self):
        order, oi = self._order_with_partial_receipt(10, 6)
        stock_before = get_current_stock(self.mi1)
        close_remaining(user=self.staff_skin, order_item=oi, quantity=4,
                        reason=RemainingCloseReason.SOLD_OUT)
        oi.refresh_from_db()
        self.assertEqual(remaining_quantity(oi), Decimal("0"))
        # 현재고 불변
        self.assertEqual(get_current_stock(self.mi1), stock_before)
        # 입고대기 목록에서 사라짐
        self.assertFalse(get_pending_order_items(self.manager).filter(pk=oi.pk).exists())
        # StockTransaction 은 입고 1건뿐(마감은 거래 미생성)
        self.assertEqual(
            StockTransaction.objects.filter(source_order_item=oi).count(), 1
        )

    def test_close_over_unprocessed_blocked(self):
        order, oi = self._order_with_partial_receipt(10, 6)
        with self.assertRaises(OrderError):
            close_remaining(user=self.staff_skin, order_item=oi, quantity=5,
                            reason=RemainingCloseReason.SOLD_OUT)

    def test_close_requires_reason(self):
        order, oi = self._order_with_partial_receipt(10, 6)
        with self.assertRaises(OrderError):
            close_remaining(user=self.staff_skin, order_item=oi, quantity=4, reason="")

    def test_completed_item_cannot_close(self):
        order, oi = self._order_with_partial_receipt(10, 10)  # 전량 입고
        with self.assertRaises(OrderError):
            close_remaining(user=self.staff_skin, order_item=oi, quantity=1,
                            reason=RemainingCloseReason.GIVE_UP)

    def test_canceled_order_cannot_close(self):
        from inventory.order_services import cancel_order
        add_to_cart(user=self.staff_skin, managed_item=self.mi1, supplier=self.sup_a, quantity=5)
        order = confirm_order(user=self.staff_skin)[0]
        oi = order.items.first()
        cancel_order(user=self.staff_skin, order=order, reason="x")
        with self.assertRaises(OrderError):
            close_remaining(user=self.staff_skin, order_item=oi, quantity=5,
                            reason=RemainingCloseReason.ORDER_CANCELED)

    def test_close_permission_out_of_scope(self):
        # 치료실 품목 주문 → 피부실 STAFF 는 마감 불가
        mi_t = create_managed_item(
            item=create_item("치료품"), department=self.dept_treatment, default_supplier=self.sup_a
        )
        approve_initial_count(mi_t, created_by=self.manager)
        add_to_cart(user=self.staff_treatment, managed_item=mi_t, supplier=self.sup_a, quantity=5)
        order = confirm_order(user=self.staff_treatment)[0]
        oi = order.items.first()
        with self.assertRaises(PermissionDeniedError):
            close_remaining(user=self.staff_skin, order_item=oi, quantity=5,
                            reason=RemainingCloseReason.SOLD_OUT)

    def test_close_shown_in_order_detail(self):
        order, oi = self._order_with_partial_receipt(10, 6)
        close_remaining(user=self.staff_skin, order_item=oi, quantity=4,
                        reason=RemainingCloseReason.REFUND, memo="환불처리")
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:order_detail", args=[order.pk]))
        self.assertContains(resp, "잔여마감")
        self.assertContains(resp, "환불")

    def test_close_via_view(self):
        order, oi = self._order_with_partial_receipt(10, 6)
        self.client.force_login(self.staff_skin)
        resp = self.client.post(
            reverse("inventory:order_item_close", args=[oi.pk]),
            {"quantity": "4", "reason": RemainingCloseReason.SOLD_OUT, "memo": ""},
        )
        self.assertEqual(resp.status_code, 302)
        oi.refresh_from_db()
        self.assertEqual(oi.remaining_closed_quantity, Decimal("4"))
        self.assertEqual(remaining_quantity(oi), Decimal("0"))

    def test_order_over_receive_still_blocked_after_partial(self):
        # 회귀: 미처리잔여 초과 입고는 계속 차단 (부분입고 6, 잔여 4 → 5 입고 차단)
        order, oi = self._order_with_partial_receipt(10, 6)
        with self.assertRaises(OrderError):
            create_stock_in_from_order_item(
                user=self.staff_skin, order_item=oi, quantity=5,
                unit_price=Decimal("1000"), no_expiration=True,
            )
