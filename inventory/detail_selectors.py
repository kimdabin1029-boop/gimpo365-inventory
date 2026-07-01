"""상세조회 전용 selector (읽기 전용). (v0.2.2)

원칙:
- 조회만 담당한다. 생성/상태변경 없음.
- 권한 범위는 기존 목록 화면과 동일하게 유지한다. (상세가 목록보다 넓어지지 않는다)
  - 관리품목: get_accessible_managed_items 범위
  - 거래: get_transactions(_accessible_transactions) 범위
  - 주문/주문품목: _accessible_orders / _accessible_order_items 범위
- 현재고 및 기입고 수량은 APPROVED 거래 기준(기존 원칙 불변).
"""

from django.db.models import Max

from accounts.permissions import is_manager_or_above
from inventory.models import (
    OUT_TRANSACTION_TYPES,
    Supplier,
    TransactionStatus,
    TransactionType,
)
from inventory.order_selectors import (
    _accessible_order_items,
    _accessible_orders,
    _annotate_item_progress,
    get_orders,
    get_pending_order_items,
    received_quantity,
    remaining_quantity,
)
from inventory.selectors import (
    _accessible_transactions,
    get_accessible_managed_items,
    get_managed_items_with_current_stock,
    get_transactions,
)

_APPROVED = TransactionStatus.APPROVED


# ---------------------------------------------------------------------------
# 관리품목 상세
# ---------------------------------------------------------------------------
def get_managed_item_detail(user, managed_item_id):
    """권한 범위 내 단일 관리품목(현재고 주석 포함). 범위 밖이면 None."""
    return (
        get_managed_items_with_current_stock(user)
        .filter(pk=managed_item_id)
        .first()
    )


def get_managed_item_stats(managed_item):
    """최근 입고/출고/주문일, 최근 입고단가, 최근 입고 유통기한 등 요약. (APPROVED 기준)"""
    approved = managed_item.stock_transactions.filter(status=_APPROVED)
    last_in_tx = (
        approved.filter(transaction_type=TransactionType.IN)
        .order_by("-occurred_at", "-id")
        .first()
    )
    last_out_at = (
        approved.filter(transaction_type__in=OUT_TRANSACTION_TYPES)
        .aggregate(m=Max("occurred_at"))["m"]
    )
    last_order_date = managed_item.order_items.aggregate(
        m=Max("order__order_date")
    )["m"]
    return {
        "last_in_at": last_in_tx.occurred_at if last_in_tx else None,
        "last_out_at": last_out_at,
        "last_order_date": last_order_date,
        "last_unit_price": last_in_tx.unit_price if last_in_tx else None,
        "last_expiration": last_in_tx.expiration_date if last_in_tx else None,
    }


def get_recent_transactions_for_managed_item(user, managed_item, limit=30):
    """관리품목 최근 거래 (권한 범위). 목록 정렬 규칙을 따른다."""
    return get_transactions(user, {"managed_item": managed_item})[:limit]


def get_recent_order_items_for_managed_item(user, managed_item, limit=20):
    """관리품목 최근 주문품목 (기입고/잔여 주석 포함, 권한 범위)."""
    qs = _annotate_item_progress(
        _accessible_order_items(user).filter(managed_item=managed_item)
    ).order_by("-order__order_date", "-order__id", "-id")
    return qs[:limit]


# ---------------------------------------------------------------------------
# 공급업체 상세
# ---------------------------------------------------------------------------
def get_supplier_detail(user, supplier_id):
    """공급업체 상세. 비관리자는 본인 권한 범위와 관련된 공급업체만 접근 가능.

    관련 판단: 본인 접근 범위 관리품목의 기본 공급업체이거나,
    본인 범위의 주문/거래에 등장하는 공급업체. 어느 것도 아니면 None.
    """
    supplier = Supplier.objects.filter(pk=supplier_id).first()
    if supplier is None:
        return None
    if is_manager_or_above(user):
        return supplier
    if get_accessible_managed_items(user).filter(default_supplier=supplier).exists():
        return supplier
    if _accessible_orders(user).filter(supplier=supplier).exists():
        return supplier
    if _accessible_transactions(user).filter(supplier=supplier).exists():
        return supplier
    return None


def get_supplier_stats(user, supplier):
    """공급업체 요약: 기본공급 품목 수, 최근 주문일/입고일, 미입고 주문품목 수. (권한 범위)"""
    default_items = get_accessible_managed_items(user).filter(
        default_supplier=supplier
    )
    last_order_date = _accessible_orders(user).filter(supplier=supplier).aggregate(
        m=Max("order_date")
    )["m"]
    last_in_at = (
        _accessible_transactions(user)
        .filter(
            supplier=supplier,
            transaction_type=TransactionType.IN,
            status=_APPROVED,
        )
        .aggregate(m=Max("occurred_at"))["m"]
    )
    unreceived_count = get_pending_order_items(user, {"supplier": supplier}).count()
    return {
        "default_item_count": default_items.count(),
        "last_order_date": last_order_date,
        "last_in_at": last_in_at,
        "unreceived_count": unreceived_count,
    }


def get_supplier_default_items(user, supplier):
    """공급업체가 기본 공급업체로 지정된 관리품목 (현재고 주석, 권한 범위)."""
    return get_managed_items_with_current_stock(user).filter(default_supplier=supplier)


def get_recent_orders_for_supplier(user, supplier, limit=20):
    return get_orders(user, {"supplier": supplier})[:limit]


def get_unreceived_order_items_for_supplier(user, supplier, limit=20):
    return get_pending_order_items(user, {"supplier": supplier})[:limit]


def get_recent_stock_ins_for_supplier(user, supplier, limit=30):
    return (
        _accessible_transactions(user)
        .filter(
            supplier=supplier,
            transaction_type=TransactionType.IN,
            status=_APPROVED,
        )
        .order_by("-occurred_at", "-id")[:limit]
    )


# ---------------------------------------------------------------------------
# 거래 상세
# ---------------------------------------------------------------------------
def get_transaction_detail(user, transaction_id):
    """권한 범위 내 단일 거래. 범위 밖이면 None. (거래이력과 동일 범위)"""
    return get_transactions(user).filter(pk=transaction_id).first()


def get_transaction_order_link(transaction):
    """거래에 연결된 주문품목 정보(있으면). 없으면 None. (v0.2.1 source_order_item)"""
    oi = transaction.source_order_item
    if oi is None:
        return None
    return {
        "order_item": oi,
        "order": oi.order,
        "ordered_quantity": oi.quantity,
        "received_quantity": received_quantity(oi),
        "remaining_quantity": remaining_quantity(oi),
    }
