"""주문 조회 전용 로직 (selector). (v0.2.0)

원칙:
- 조회만 담당한다. 상태 변경/생성은 order_services.py 에서 수행한다.
- 권한 범위:
  - STAFF / TEAM_LEADER → 본인 또는 본인 부서(주문자 기준) 주문
  - MANAGER / ADMIN → 전체 주문
  TODO(권한): OrderItem 이 여러 부서에 걸칠 수 있으나, MVP 는 주문자(ordered_by)의 부서를
  기준으로 범위를 판정한다. 부서 교차 주문 정책은 추후 확정.
"""

from django.db.models import Count, Q

from accounts.permissions import is_manager_or_above
from inventory.models import Order, OrderStatus


def _accessible_orders(user):
    qs = Order.objects.select_related("supplier", "ordered_by", "ordered_by__department")
    if is_manager_or_above(user):
        return qs
    dept_id = getattr(user, "department_id", None)
    if dept_id is None:
        # 부서가 없는 비관리자는 본인 주문만
        return qs.filter(ordered_by=user)
    return qs.filter(Q(ordered_by=user) | Q(ordered_by__department_id=dept_id))


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
