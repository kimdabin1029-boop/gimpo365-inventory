"""주문(장바구니/주문) service. (v0.2.0)

원칙:
- 주문은 현재고를 변경하지 않는다. 실제 재고 증가는 입고(StockTransaction IN)로만 발생한다.
  (이 모듈은 StockTransaction 을 생성/수정하지 않는다.)
- 장바구니/주문 변경은 이 모듈의 service 함수로만 수행한다. (View/Admin 직접 create/save 금지)
- 권한: 추가/생성은 STAFF 이상(접근 가능한 관리품목), 취소/입고완료는 MANAGER 이상 또는 주문자 본인.
"""

from collections import OrderedDict
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from accounts.permissions import is_manager_or_above
from inventory.exceptions import (
    OrderError,
    PermissionDeniedError,
)
from inventory.models import (
    CartItem,
    Order,
    OrderCart,
    OrderItem,
    OrderStatus,
)
from inventory.permissions import can_access_managed_item

# update_cart_item 에서 "supplier 미전달"과 "supplier=None(공급업체 지움)"을 구분하기 위한 sentinel
_UNSET = object()


# ---------------------------------------------------------------------------
# 공통 helper
# ---------------------------------------------------------------------------
def _to_positive_quantity(value) -> Decimal:
    try:
        qty = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise OrderError("수량이 올바른 숫자가 아닙니다.")
    if qty <= 0:
        raise OrderError("수량은 0보다 커야 합니다.")
    return qty


def generate_internal_order_no(order_date=None, *, site_prefix="") -> str:
    """내부 주문번호 생성. 형식: YYMMDD-순번 (같은 날짜 내 중복 없음). (v0.2.0)

    다중 지점 확장 시 site_prefix 로 지점 구분을 덧붙일 수 있도록 helper 로 분리한다.
    TODO(multi-site): site_prefix 정책(예: 'GP-260701-1')은 지점 도입 시 확정.

    동시성: 같은 날짜에 대해 매우 드물게 경합이 발생하면 internal_order_no unique 제약이
    막아준다(이 경우 호출측에서 재시도). 단일 지점/저빈도 환경 기준 MVP.
    """
    if order_date is None:
        order_date = timezone.localdate()
    prefix = f"{site_prefix}{order_date.strftime('%y%m%d')}"
    existing = Order.objects.filter(
        internal_order_no__startswith=f"{prefix}-"
    ).values_list("internal_order_no", flat=True)
    max_seq = 0
    for no in existing:
        try:
            max_seq = max(max_seq, int(no.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{prefix}-{max_seq + 1}"


# ---------------------------------------------------------------------------
# 장바구니 service
# ---------------------------------------------------------------------------
def get_or_create_cart(user) -> OrderCart:
    cart, _ = OrderCart.objects.get_or_create(user=user)
    return cart


def _check_can_order_item(user, managed_item):
    """장바구니 추가 권한: 접근 가능한(권한 범위) 활성 관리품목만."""
    if not can_access_managed_item(user, managed_item):
        raise PermissionDeniedError("해당 관리품목을 주문할 권한이 없습니다.")
    if not managed_item.is_active:
        raise OrderError("비활성 관리품목은 주문 장바구니에 담을 수 없습니다.")


@transaction.atomic
def add_to_cart(*, user, managed_item, supplier=None, quantity=1, memo=""):
    """장바구니에 담기. 같은 (managed_item + supplier) 조합이면 수량을 증가시킨다. (v0.2.0)

    supplier 미지정 시 해당 품목의 기본 공급업체를 초기값으로 사용한다(없으면 None).
    """
    _check_can_order_item(user, managed_item)
    qty = _to_positive_quantity(quantity)
    if supplier is None:
        supplier = managed_item.default_supplier

    cart = get_or_create_cart(user)
    existing = (
        cart.items.select_for_update()
        .filter(managed_item=managed_item, supplier=supplier)
        .first()
    )
    if existing:
        existing.quantity = existing.quantity + qty
        if memo:
            existing.memo = memo
        existing.save(update_fields=["quantity", "memo", "updated_at"])
        return existing

    return CartItem.objects.create(
        cart=cart,
        managed_item=managed_item,
        supplier=supplier,
        quantity=qty,
        memo=memo,
    )


def _get_owned_cart_item(user, cart_item_id) -> CartItem:
    try:
        return CartItem.objects.select_related("cart").get(
            pk=cart_item_id, cart__user=user
        )
    except CartItem.DoesNotExist:
        raise OrderError("장바구니 항목을 찾을 수 없습니다.")


@transaction.atomic
def update_cart_item(*, user, cart_item_id, quantity=None, supplier=_UNSET, memo=None):
    """장바구니 항목 수정 (수량/공급업체/메모). 본인 장바구니만."""
    item = _get_owned_cart_item(user, cart_item_id)
    fields = ["updated_at"]
    if quantity is not None:
        item.quantity = _to_positive_quantity(quantity)
        fields.append("quantity")
    if supplier is not _UNSET:
        item.supplier = supplier
        fields.append("supplier")
    if memo is not None:
        item.memo = memo
        fields.append("memo")
    item.save(update_fields=fields)
    return item


@transaction.atomic
def remove_cart_item(*, user, cart_item_id):
    """장바구니 항목 삭제. 본인 장바구니만."""
    item = _get_owned_cart_item(user, cart_item_id)
    item.delete()


# ---------------------------------------------------------------------------
# 주문 확정 service
# ---------------------------------------------------------------------------
@transaction.atomic
def confirm_order(*, user, order_date=None, external_order_no="", memo=""):
    """장바구니를 공급업체별로 분리해 Order/OrderItem 을 생성한다. (v0.2.0)

    - 공급업체별로 Order 1건 생성 (각 Order 는 단일 supplier).
    - 생성 상태는 ORDERED. 현재고는 변경하지 않는다.
    - 확정 후 장바구니는 비운다.
    - 공급업체가 지정되지 않은 항목이 있으면 차단(각 Order 는 supplier 필수).
    """
    cart = get_or_create_cart(user)
    items = list(
        cart.items.select_related("managed_item", "supplier").order_by("id")
    )
    if not items:
        raise OrderError("장바구니가 비어 있어 주문을 확정할 수 없습니다.")

    missing = [ci for ci in items if ci.supplier_id is None]
    if missing:
        names = ", ".join(ci.managed_item.item.name for ci in missing)
        raise OrderError(
            f"공급업체가 지정되지 않은 항목이 있어 주문할 수 없습니다: {names}. "
            "장바구니에서 공급업체를 선택해주세요."
        )

    if order_date is None:
        order_date = timezone.localdate()

    # 공급업체별 그룹 (입력 순서 유지)
    groups: "OrderedDict[int, list]" = OrderedDict()
    for ci in items:
        groups.setdefault(ci.supplier_id, []).append(ci)

    created = []
    for supplier_id, citems in groups.items():
        supplier = citems[0].supplier
        order = Order.objects.create(
            internal_order_no=generate_internal_order_no(order_date),
            external_order_no=external_order_no,
            supplier=supplier,
            ordered_by=user,
            order_date=order_date,
            memo=memo,
        )
        for ci in citems:
            OrderItem.objects.create(
                order=order,
                managed_item=ci.managed_item,
                quantity=ci.quantity,
                memo=ci.memo,
            )
        created.append(order)

    cart.items.all().delete()
    return created


# ---------------------------------------------------------------------------
# 주문 상태 변경 service (현재고와 무관)
# ---------------------------------------------------------------------------
def can_manage_order(user, order) -> bool:
    """취소/입고완료 권한: MANAGER 이상 또는 주문자 본인."""
    return is_manager_or_above(user) or order.ordered_by_id == getattr(user, "id", None)


@transaction.atomic
def cancel_order(*, user, order, reason=""):
    """ORDERED 주문 취소 → CANCELED. 현재고에 영향을 주지 않는다. (v0.2.0)

    RECEIVED 주문은 취소할 수 없다. 취소자/취소일시 기록, 사유는 memo 에 덧붙인다.
    """
    order = Order.objects.select_for_update().get(pk=order.pk)
    if not can_manage_order(user, order):
        raise PermissionDeniedError("주문을 취소할 권한이 없습니다. (주문자 본인 또는 MANAGER 이상)")
    if order.status == OrderStatus.RECEIVED:
        raise OrderError("입고완료된 주문은 취소할 수 없습니다.")
    if order.status != OrderStatus.ORDERED:
        raise OrderError("주문완료(ORDERED) 상태의 주문만 취소할 수 있습니다.")

    order.status = OrderStatus.CANCELED
    order.canceled_by = user
    order.canceled_at = timezone.now()
    if reason:
        stamp = timezone.localtime(order.canceled_at).strftime("%Y-%m-%d %H:%M")
        prefix = f"{order.memo}\n" if order.memo else ""
        order.memo = f"{prefix}[취소사유 {stamp}] {reason}"
    order.save(
        update_fields=["status", "canceled_by", "canceled_at", "memo", "updated_at"]
    )
    return order


@transaction.atomic
def mark_order_received(*, user, order):
    """ORDERED 주문 → RECEIVED. 현재고를 증가시키지 않는다(입고 등록과 별개). (v0.2.0)

    실제 재고 증가는 기존 입고 등록(create_stock_in)으로만 처리한다.
    """
    order = Order.objects.select_for_update().get(pk=order.pk)
    if not can_manage_order(user, order):
        raise PermissionDeniedError(
            "입고완료 처리 권한이 없습니다. (주문자 본인 또는 MANAGER 이상)"
        )
    if order.status == OrderStatus.CANCELED:
        raise OrderError("취소된 주문은 입고완료 처리할 수 없습니다.")
    if order.status != OrderStatus.ORDERED:
        raise OrderError("주문완료(ORDERED) 상태의 주문만 입고완료 처리할 수 있습니다.")

    order.status = OrderStatus.RECEIVED
    order.received_by = user
    order.received_at = timezone.now()
    order.save(
        update_fields=["status", "received_by", "received_at", "updated_at"]
    )
    return order
