"""주문 조회 전용 로직 (selector). (v0.2.0)

원칙:
- 조회만 담당한다. 상태 변경/생성은 order_services.py 에서 수행한다.
- 권한 범위:
  - STAFF / TEAM_LEADER → 본인 또는 본인 부서(주문자 기준) 주문
  - MANAGER / ADMIN → 전체 주문
  TODO(권한): OrderItem 이 여러 부서에 걸칠 수 있으나, MVP 는 주문자(ordered_by)의 부서를
  기준으로 범위를 판정한다. 부서 교차 주문 정책은 추후 확정.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounts.permissions import is_manager_or_above
from inventory.models import Order, OrderItem, OrderStatus, TransactionStatus

_APPROVED = TransactionStatus.APPROVED
_ZERO = Value(Decimal("0"), output_field=DecimalField(max_digits=12, decimal_places=3))


def _apply_order_dept_filter(qs, user, filters):
    """주문 목록 부서 필터. MANAGER/ADMIN 만 유효. 비관리자에는 무시(권한 범위 유지)."""
    if not filters:
        return qs
    department = filters.get("department")
    if department and is_manager_or_above(user):
        qs = qs.filter(ordered_by__department=department)
    return qs


def _accessible_orders(user):
    qs = Order.objects.select_related("supplier", "ordered_by", "ordered_by__department")
    if is_manager_or_above(user):
        return qs
    dept_id = getattr(user, "department_id", None)
    if dept_id is None:
        # 부서가 없는 비관리자는 본인 주문만
        return qs.filter(ordered_by=user)
    return qs.filter(Q(ordered_by=user) | Q(ordered_by__department_id=dept_id))


# ---------------------------------------------------------------------------
# OrderItem 기입고/잔여 수량 (기준: APPROVED 입고거래 합계) (v0.2.1)
# ---------------------------------------------------------------------------
def received_quantity(order_item) -> Decimal:
    """OrderItem 기입고 수량 = source_order_item 으로 연결된 APPROVED 거래 합계.

    입고거래가 취소되면 APPROVED 가 아니게 되어 자동으로 제외된다. (현재고 원칙과 동일)
    """
    total = order_item.stock_transactions.filter(status=_APPROVED).aggregate(
        s=Sum("quantity_delta")
    )["s"]
    return total if total is not None else Decimal("0")


def remaining_quantity(order_item) -> Decimal:
    """OrderItem 잔여 수량 = 주문수량 - 기입고 수량."""
    return order_item.quantity - received_quantity(order_item)


def _annotate_item_progress(qs):
    """OrderItem queryset 에 received_qty / remaining_qty 주석."""
    return qs.annotate(
        received_qty=Coalesce(
            Sum(
                "stock_transactions__quantity_delta",
                filter=Q(stock_transactions__status=_APPROVED),
            ),
            _ZERO,
        )
    ).annotate(remaining_qty=F("quantity") - F("received_qty"))


def get_order_items_with_progress(order):
    """주문 상세용: 해당 주문의 OrderItem + 기입고/잔여 주석 (+ 연결 입고거래 prefetch)."""
    return _annotate_item_progress(
        order.items.select_related(
            "managed_item", "managed_item__item", "managed_item__department"
        ).prefetch_related("stock_transactions")
    ).order_by("id")


def _accessible_order_items(user):
    qs = OrderItem.objects.select_related(
        "order", "order__supplier", "order__ordered_by",
        "managed_item", "managed_item__item", "managed_item__department",
    )
    if is_manager_or_above(user):
        return qs
    dept_id = getattr(user, "department_id", None)
    if dept_id is None:
        return qs.filter(order__ordered_by=user)
    return qs.filter(
        Q(order__ordered_by=user) | Q(order__ordered_by__department_id=dept_id)
    )


def get_order_item_for_user_or_none(user, pk):
    """권한 범위 내 단일 OrderItem (없으면 None)."""
    return _accessible_order_items(user).filter(pk=pk).first()


def get_pending_order_items(user, filters: dict | None = None):
    """입고대기 품목: 잔여수량 > 0 이고 취소되지 않은 주문의 OrderItem. (v0.2.1)

    필터: supplier / department(MANAGER·ADMIN만) / order_date / overdue(7일 이상 미입고).
    """
    qs = _annotate_item_progress(
        _accessible_order_items(user).exclude(order__status=OrderStatus.CANCELED)
    ).filter(remaining_qty__gt=0)

    if filters:
        supplier = filters.get("supplier")
        if supplier:
            qs = qs.filter(order__supplier=supplier)
        department = filters.get("department")
        if department and is_manager_or_above(user):
            qs = qs.filter(order__ordered_by__department=department)
        order_date = filters.get("order_date")
        if order_date:
            qs = qs.filter(order__order_date=order_date)
        if filters.get("overdue"):
            cutoff = timezone.localdate() - timedelta(days=7)
            qs = qs.filter(order__order_date__lte=cutoff)
    return qs.order_by("order__order_date", "order__id", "id")


def get_orders(user, filters: dict | None = None):
    """권한 범위 내 주문 목록 (주문 품목 수 주석 포함)."""
    qs = (
        _accessible_orders(user)
        .annotate(item_count=Count("items"))
        .order_by("-ordered_at", "-id")
    )
    if filters:
        status = filters.get("status")
        if status:
            qs = qs.filter(status=status)
        supplier = filters.get("supplier")
        if supplier:
            qs = qs.filter(supplier=supplier)
        qs = _apply_order_dept_filter(qs, user, filters)
    return qs


def get_order_or_none(user, pk):
    """권한 범위 내 단일 주문 (없으면 None)."""
    return (
        _accessible_orders(user)
        .annotate(item_count=Count("items"))
        .filter(pk=pk)
        .first()
    )


def get_unreceived_orders(user, limit=None):
    """미입고(ORDERED) 주문. 대시보드용."""
    qs = get_orders(user, {"status": OrderStatus.ORDERED})
    if limit is not None:
        return qs[:limit]
    return qs
