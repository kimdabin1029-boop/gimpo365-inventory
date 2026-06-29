"""조회 전용 로직 (selector). (TECH_SPEC §10)

원칙:
- selector 는 순수 조회만 담당한다.
- 락을 걸지 않는다. (select_for_update 사용 금지)
- get_current_stock_for_update 는 만들지 않는다. (TECH_SPEC §0)
"""

from decimal import Decimal

from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce

from accounts.permissions import is_manager_or_above
from inventory.models import (
    ManagedItem,
    StockTransaction,
    TransactionStatus,
    TransactionType,
)

# 현재고 계산에 반영되는 거래 상태 (TECH_SPEC §6.5)
_APPROVED = TransactionStatus.APPROVED

# 승인 큐 대상 거래 유형 (PRODUCT_SPEC §10.12)
PENDING_QUEUE_TYPES = [
    TransactionType.INITIAL_COUNT,
    TransactionType.ADJUSTMENT,
]

_DECIMAL_ZERO = Value(Decimal("0"), output_field=DecimalField(max_digits=12, decimal_places=3))


def get_current_stock(managed_item: ManagedItem) -> Decimal:
    """현재고 = APPROVED 거래의 quantity_delta 합계. (TECH_SPEC §6.5)"""
    total = managed_item.stock_transactions.filter(status=_APPROVED).aggregate(
        s=Sum("quantity_delta")
    )["s"]
    return total if total is not None else Decimal("0")


def get_accessible_managed_items(user):
    """사용자가 접근 가능한 ManagedItem queryset.

    - STAFF / TEAM_LEADER → 본인 부서만
    - MANAGER / ADMIN → 전체 부서
    - active_for_inventory=False 부서는 모두에게서 제외 (PRODUCT_SPEC §7.1)
    """
    qs = ManagedItem.objects.select_related(
        "item", "department", "default_supplier"
    ).filter(department__active_for_inventory=True)

    if is_manager_or_above(user):
        return qs

    if getattr(user, "department_id", None) is None:
        return qs.none()
    return qs.filter(department_id=user.department_id)


def _annotate_current_stock(qs):
    """각 ManagedItem 에 current_stock 주석을 단다 (N+1 방지). (TECH_SPEC §15.5)"""
    return qs.annotate(
        current_stock=Coalesce(
            Sum(
                "stock_transactions__quantity_delta",
                filter=Q(stock_transactions__status=_APPROVED),
            ),
            _DECIMAL_ZERO,
        )
    )


def _apply_managed_item_filters(qs, filters):
    if not filters:
        return qs
    department = filters.get("department")
    if department:
        qs = qs.filter(department=department)
    category = filters.get("category")
    if category:
        qs = qs.filter(item__category=category)
    storage_location = filters.get("storage_location")
    if storage_location:
        qs = qs.filter(storage_location__icontains=storage_location)
    is_active = filters.get("is_active")
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    return qs


def get_managed_items_with_current_stock(user, filters: dict | None = None):
    """현재고 주석이 달린 접근 가능 ManagedItem 목록."""
    qs = _annotate_current_stock(get_accessible_managed_items(user))
    qs = _apply_managed_item_filters(qs, filters)
    if filters and filters.get("low_stock"):
        qs = qs.filter(current_stock__lte=F("minimum_stock"))
    return qs


def get_low_stock_managed_items(user, filters: dict | None = None):
    """최소재고 이하(현재고 <= 최소재고) 품목. (PRODUCT_SPEC §5.9)"""
    qs = get_managed_items_with_current_stock(user, filters)
    return qs.filter(current_stock__lte=F("minimum_stock"))


def _accessible_transactions(user):
    qs = StockTransaction.objects.select_related(
        "managed_item",
        "managed_item__item",
        "managed_item__department",
        "created_by",
        "approved_by",
        "canceled_by",
        "supplier",
    )
    if is_manager_or_above(user):
        return qs
    if getattr(user, "department_id", None) is None:
        return qs.none()
    return qs.filter(managed_item__department_id=user.department_id)


def get_transactions(user, filters: dict | None = None):
    """거래 이력 조회. (PRODUCT_SPEC §10.14)

    - STAFF / TEAM_LEADER → 본인 부서 거래
    - MANAGER / ADMIN → 전체 거래
    정렬은 모델 Meta(-occurred_at, -created_at, -id)를 따른다.
    """
    qs = _accessible_transactions(user)
    if filters:
        department = filters.get("department")
        if department:
            qs = qs.filter(managed_item__department=department)
        managed_item = filters.get("managed_item")
        if managed_item:
            qs = qs.filter(managed_item=managed_item)
        transaction_type = filters.get("transaction_type")
        if transaction_type:
            qs = qs.filter(transaction_type=transaction_type)
        status = filters.get("status")
        if status:
            qs = qs.filter(status=status)
    return qs


def get_pending_transactions(user, filters: dict | None = None):
    """승인 큐: PENDING 상태의 INITIAL_COUNT / ADJUSTMENT. (PRODUCT_SPEC §10.12)"""
    return get_transactions(user, filters).filter(
        status=TransactionStatus.PENDING,
        transaction_type__in=PENDING_QUEUE_TYPES,
    )


def has_approved_initial_count(managed_item: ManagedItem) -> bool:
    """해당 ManagedItem 에 APPROVED INITIAL_COUNT 가 존재하는지. (TECH_SPEC §10)"""
    return managed_item.stock_transactions.filter(
        transaction_type=TransactionType.INITIAL_COUNT,
        status=_APPROVED,
    ).exists()


def has_pending_initial_count(managed_item: ManagedItem) -> bool:
    """해당 ManagedItem 에 PENDING(승인대기) INITIAL_COUNT 가 존재하는지.

    최초재고 승인 전 일반 거래(입고/출고/실사조정) 차단 및
    중복 최초재고 요청 차단에 사용한다. (HOTFIX)
    """
    return managed_item.stock_transactions.filter(
        transaction_type=TransactionType.INITIAL_COUNT,
        status=TransactionStatus.PENDING,
    ).exists()
