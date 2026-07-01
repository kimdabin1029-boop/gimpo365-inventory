"""v0.2.1 주문서-입고 반자동화 + 사용성 테스트.

핵심 불변식: 주문/주문상태 변경은 현재고를 바꾸지 않는다.
실제 재고 증가는 주문서 기반 입고등록이 create_stock_in 으로 만든 APPROVED 입고거래로만 발생한다.
"""

from datetime import timedelta
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
    ItemCategory,
    Order,
    OrderStatus,
    StockTransaction,
    TransactionStatus,
    TransactionType,
)
from inventory.order_selectors import (
    get_pending_order_items,
    received_quantity,
    remaining_quantity,
)
from inventory.order_services import (
    add_to_cart,
    confirm_order,
    create_stock_in_from_order_item,
)
from inventory.selectors import get_current_stock
from inventory.services import cancel_transaction


class OrderInboundFixture:
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.sup = create_supplier(name="A업체")
        cls.item1 = create_item("알콜솜", category=ItemCategory.HYGIENE_SUPPLY)
        cls.item2 = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi1 = create_managed_item(
            item=cls.item1, department=cls.dept_skin, default_supplier=cls.sup
        )
        cls.mi2 = create_managed_item(
            item=cls.item2, department=cls.dept_skin, default_supplier=cls.sup
        )
        # 입고 전제: 승인된 최초재고(수량 0)
        approve_initial_count(cls.mi1, created_by=cls.manager)
        approve_initial_count(cls.mi2, created_by=cls.manager)

    def _order(self, user=None, items=((10,),)):
        """items: 각 관리품목/수량. 기본 mi1 10개 주문."""
        user = user or self.staff_skin
        add_to_cart(user=user, managed_item=self.mi1, supplier=self.sup, quantity=items[0][0])
        if len(items) > 1:
            add_to_cart(user=user, managed_item=self.mi2, supplier=self.sup, quantity=items[1][0])
        return confirm_order(user=user)[0]

    def _inbound(self, order_item, qty, *, user=None, **kw):
        user = user or self.staff_skin
        kw.setdefault("unit_price", Decimal("1000"))
        kw.setdefault("no_expiration", True)
        return create_stock_in_from_order_item(
            user=user, order_item=order_item, quantity=qty, **kw
        )


class OrderStockPrincipleTest(OrderInboundFixture, BaseFixtureTestCase):
    # 1. 주문 확정만으로 현재고 불변
    def test_confirm_does_not_change_stock(self):
        self._order()
        self.assertEqual(get_current_stock(self.mi1), Decimal("0"))

    # 3 & 4 & 5. 주문서 기반 입고등록 → APPROVED IN 생성 + 현재고 증가 + source 연결
    def test_inbound_creates_approved_in_and_increases_stock(self):
        order = self._order()
        oi = order.items.first()
        tx = self._inbound(oi, 4)
        self.assertEqual(tx.transaction_type, TransactionType.IN)
        self.assertEqual(tx.status, TransactionStatus.APPROVED)
        self.assertEqual(tx.source_order_item_id, oi.pk)
        self.assertEqual(get_current_stock(self.mi1), Decimal("4"))

    # 6. 입고거래 취소 → 기입고 수량 감소
    def test_cancel_inbound_reduces_received(self):
        order = self._order()
        oi = order.items.first()
        tx = self._inbound(oi, 4)
        self.assertEqual(received_quantity(oi), Decimal("4"))
        cancel_transaction(user=self.staff_skin, transaction_obj=tx, cancel_reason="오입력")
        self.assertEqual(received_quantity(oi), Decimal("0"))
        self.assertEqual(get_current_stock(self.mi1), Decimal("0"))


class PartialReceiveTest(OrderInboundFixture, BaseFixtureTestCase):
    # 부분입고 1: 10 중 6 → 부분입고 (잔여 4)
    def test_partial_item(self):
        order = self._order()
        oi = order.items.first()
        self._inbound(oi, 6)
        self.assertEqual(received_quantity(oi), Decimal("6"))
        self.assertEqual(remaining_quantity(oi), Decimal("4"))
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PARTIALLY_RECEIVED)

    # 부분입고 2: 10 중 10 → 입고완료
    def test_full_item(self):
        order = self._order()
        oi = order.items.first()
        self._inbound(oi, 10)
        self.assertEqual(remaining_quantity(oi), Decimal("0"))
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.RECEIVED)

    # 부분입고 3: 여러 품목 중 일부만 입고 → Order PARTIALLY_RECEIVED
    def test_order_partial_when_some_items_pending(self):
        order = self._order(items=((10,), (5,)))
        first = order.items.first()
        self._inbound(first, 10)  # 첫 품목만 완료, 둘째 미입고
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PARTIALLY_RECEIVED)

    # 부분입고 4: 모든 품목 입고 → RECEIVED
    def test_order_received_when_all_items_done(self):
        order = self._order(items=((10,), (5,)))
        for oi in order.items.all():
            self._inbound(oi, oi.quantity)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.RECEIVED)
        self.assertEqual(order.received_by, self.staff_skin)

    # 부분입고 5: 입고완료 OrderItem 추가 입고 불가
    def test_completed_item_cannot_inbound_more(self):
        order = self._order()
        oi = order.items.first()
        self._inbound(oi, 10)
        with self.assertRaises(OrderError):
            self._inbound(oi, 1)


class OverReceiveTest(OrderInboundFixture, BaseFixtureTestCase):
    def test_over_remaining_blocked_with_message_and_no_tx(self):
        order = self._order()
        oi = order.items.first()
        self._inbound(oi, 6)  # 잔여 4
        before = StockTransaction.objects.count()
        with self.assertRaises(OrderError) as ctx:
            self._inbound(oi, 5)  # 잔여 4 초과
        msg = str(ctx.exception)
        self.assertIn("잔여", msg)
        self.assertIn("일반 입고등록", msg)
        self.assertIn("추가증정", msg)
        # 초과 차단 시 거래 미생성
        self.assertEqual(StockTransaction.objects.count(), before)


class InboundValidationTest(OrderInboundFixture, BaseFixtureTestCase):
    def test_unit_price_required(self):
        order = self._order()
        oi = order.items.first()
        with self.assertRaises(OrderError):
            create_stock_in_from_order_item(
                user=self.staff_skin, order_item=oi, quantity=1,
                unit_price=None, no_expiration=True,
            )

    def test_unit_price_zero_blocked(self):
        order = self._order()
        oi = order.items.first()
        with self.assertRaises(OrderError):
            create_stock_in_from_order_item(
                user=self.staff_skin, order_item=oi, quantity=1,
                unit_price=Decimal("0"), no_expiration=True,
            )

    def test_expiration_required(self):
        order = self._order()
        oi = order.items.first()
        with self.assertRaises(OrderError):
            create_stock_in_from_order_item(
                user=self.staff_skin, order_item=oi, quantity=1,
                unit_price=Decimal("1000"), expiration_date=None, no_expiration=False,
            )

    def test_no_expiration_sets_occurred_plus_3y(self):
        order = self._order()
        oi = order.items.first()
        occurred = timezone.now()
        tx = create_stock_in_from_order_item(
            user=self.staff_skin, order_item=oi, quantity=1,
            occurred_at=occurred, unit_price=Decimal("1000"), no_expiration=True,
        )
        expected = timezone.localdate(occurred).replace(
            year=timezone.localdate(occurred).year + 3
        )
        self.assertEqual(tx.expiration_date, expected)


class InboundPermissionTest(OrderInboundFixture, BaseFixtureTestCase):
    def test_staff_cannot_inbound_out_of_scope(self):
        # 치료실 관리품목 주문 (치료실 staff 가 주문)
        mi_treat = create_managed_item(
            item=self.item1, department=self.dept_treatment, default_supplier=self.sup
        )
        approve_initial_count(mi_treat, created_by=self.manager)
        add_to_cart(user=self.staff_treatment, managed_item=mi_treat, supplier=self.sup, quantity=3)
        order = confirm_order(user=self.staff_treatment)[0]
        oi = order.items.first()
        with self.assertRaises(PermissionDeniedError):
            self._inbound(oi, 1, user=self.staff_skin)


class InboundPendingSelectorTest(OrderInboundFixture, BaseFixtureTestCase):
    def test_only_remaining_items_listed(self):
        order = self._order(items=((10,), (5,)))
        first = order.items.first()
        self._inbound(first, 10)  # 완료 → 목록에서 제외
        items = list(get_pending_order_items(self.manager))
        # 둘째 품목(잔여 5)만 남는다
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].remaining_qty, Decimal("5"))

    def test_canceled_order_items_excluded(self):
        from inventory.order_services import cancel_order
        order = self._order()
        cancel_order(user=self.staff_skin, order=order, reason="취소")
        self.assertEqual(get_pending_order_items(self.manager).count(), 0)


class DeptFilterTest(OrderInboundFixture, BaseFixtureTestCase):
    def test_manager_sees_department_filter(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:order_list"))
        self.assertContains(resp, 'name="department"')

    def test_staff_no_department_filter(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:order_list"))
        self.assertNotContains(resp, 'name="department"')

    def test_staff_query_param_does_not_widen(self):
        # 치료실 staff 주문 생성
        mi_treat = create_managed_item(
            item=self.item2, department=self.dept_treatment, default_supplier=self.sup
        )
        approve_initial_count(mi_treat, created_by=self.manager)
        add_to_cart(user=self.staff_treatment, managed_item=mi_treat, supplier=self.sup, quantity=2)
        confirm_order(user=self.staff_treatment)
        # 피부실 staff 가 department 파라미터로 치료실을 강제해도 조회 안 됨
        self.client.force_login(self.staff_skin)
        resp = self.client.get(
            reverse("inventory:order_list") + f"?department={self.dept_treatment.pk}"
        )
        self.assertEqual(len(resp.context["orders"]), 0)


class StockUnifyAndUXTest(OrderInboundFixture, BaseFixtureTestCase):
    def test_stock_list_low_filter(self):
        # mi1/mi2 는 초기재고 0, 최소재고 0 → 최소재고 이하로 표시되려면 min 설정 필요
        mi_low = create_managed_item(
            item=create_item("붕대"), department=self.dept_skin,
            default_supplier=self.sup, minimum_stock=5,
        )
        approve_initial_count(mi_low, created_by=self.manager)  # 현재고 0 <= 5
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:stock_list") + "?filter=low_stock")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "붕대")

    def test_low_stock_menu_redirects(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:low_stock"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("filter=low_stock", resp.url)

    def test_order_detail_shows_inbound_form(self):
        order = self._order()
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:order_detail", args=[order.pk]))
        self.assertContains(resp, "입고등록")
        self.assertContains(resp, 'name="quantity_input"')

    def test_completed_item_no_inbound_form(self):
        order = self._order()
        oi = order.items.first()
        self._inbound(oi, 10)  # 완료
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:order_detail", args=[order.pk]))
        self.assertNotContains(resp, 'name="quantity_input"')

    def test_inbound_pending_lists_remaining_only(self):
        self._order()  # mi1 10개 미입고
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:inbound_pending"))
        self.assertContains(resp, self.item1.name)

    def test_no_order_receive_url(self):
        # v0.2.1: Order 단위 입고완료 URL 제거
        from django.urls import NoReverseMatch
        with self.assertRaises(NoReverseMatch):
            reverse("inventory:order_receive", args=[1])

    def test_order_item_inbound_via_view(self):
        order = self._order()
        oi = order.items.first()
        self.client.force_login(self.staff_skin)
        resp = self.client.post(
            reverse("inventory:order_item_stock_in", args=[oi.pk]),
            data={
                "quantity_input": "4",
                "occurred_at": timezone.localdate().strftime("%Y-%m-%d"),
                "unit_price": "1500",
                "no_expiration": "on",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(get_current_stock(self.mi1), Decimal("4"))
        tx = StockTransaction.objects.get(source_order_item=oi)
        self.assertEqual(tx.unit_price, Decimal("1500"))


class SessionSettingsTest(BaseFixtureTestCase):
    def test_session_expiry_settings(self):
        from django.conf import settings
        self.assertEqual(settings.SESSION_COOKIE_AGE, 60 * 60 * 2)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)
        self.assertTrue(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)
