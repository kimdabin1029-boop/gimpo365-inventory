"""리포트/내보내기용 조회 로직. (v0.2.4 · 읽기 전용)

원칙:
- 현재고/집계는 반드시 APPROVED StockTransaction 기준. (기존 원칙 불변)
- 기존 selector(get_transactions / _accessible_transactions 등)를 재사용해 권한 범위를 유지한다.
- 취소(CANCELED)/반려(REJECTED)/대기(PENDING) 거래는 집계에서 제외(=APPROVED 만).
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import (
    DecimalField,
    ExpressionWrapper,
    F,
    Max,
    Q,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_date

from inventory.models import (
    OUT_TRANSACTION_TYPES,
    TransactionStatus,
    TransactionType,
)
from inventory.selectors import _accessible_transactions, get_transactions

_APPROVED = TransactionStatus.APPROVED
_ZERO = Value(Decimal("0"), output_field=DecimalField(max_digits=20, decimal_places=3))
_AMOUNT = ExpressionWrapper(
    F("quantity_input") * F("unit_price"),
    output_field=DecimalField(max_digits=20, decimal_places=3),
)


# ---------------------------------------------------------------------------
# 거래이력 내보내기 (화면 필터/기간을 그대로 반영, 페이지네이션 무관 전체)
# ---------------------------------------------------------------------------
def resolve_tx_date_range(get_params):
    """거래이력 화면과 동일한 거래일자(occurred_at) 기간 해석. 기본 오늘~오늘."""
    today = timezone.localdate()
    rng = get_params.get("range")
    if rng == "7d":
        return today - timedelta(days=6), today
    if rng == "month":
        return today.replace(day=1), today
    if rng == "3m":
        return today - timedelta(days=90), today
    if rng == "today":
        return today, today
    gf = parse_date(get_params.get("date_from") or "")
    gt = parse_date(get_params.get("date_to") or "")
    if gf or gt:
        return gf, gt
    return today, today


def get_export_transactions(user, filters, date_from, date_to):
    """거래이력 내보내기 queryset (권한 범위 + 필터 + 기간). 페이지네이션 없음."""
    qs = get_transactions(user, filters)
    if date_from:
        qs = qs.filter(occurred_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(occurred_at__date__lte=date_to)
    return qs


# ---------------------------------------------------------------------------
# 월간 입출고 요약 (APPROVED 기준)
# ---------------------------------------------------------------------------
def get_monthly_summary(user, start, end, filters=None):
    """관리품목별 입고/출고/순증감/입고금액/최근입고·출고일 요약.

    - APPROVED 거래만 집계 (CANCELED/REJECTED/PENDING 제외).
    - 입고수량 = APPROVED 입고(IN) quantity_input 합계
    - 출고수량 = APPROVED 출고(OUT 계열) quantity_input 합계
    - 순증감 = 입고수량 - 출고수량
    - 입고금액 = Σ(입고 quantity_input × unit_price) (단가 없으면 해당 건 0 취급)
    - 기간 내 활동(APPROVED 거래)이 있는 품목만 행으로 만든다.
    """
    filters = filters or {}
    qs = _accessible_transactions(user).filter(status=_APPROVED)
    if start:
        qs = qs.filter(occurred_at__date__gte=start)
    if end:
        qs = qs.filter(occurred_at__date__lte=end)

    department = filters.get("department")
    if department:
        qs = qs.filter(managed_item__department=department)
    supplier = filters.get("supplier")
    if supplier:
        qs = qs.filter(managed_item__default_supplier=supplier)
    item_query = filters.get("item_query")
    if item_query:
        qs = qs.filter(managed_item__item__name__icontains=item_query)

    in_q = Q(transaction_type=TransactionType.IN)
    out_q = Q(transaction_type__in=OUT_TRANSACTION_TYPES)

    rows = (
        qs.values(
            "managed_item",
            "managed_item__department__name",
            "managed_item__item__name",
            "managed_item__item__specification",
        )
        .annotate(
            in_qty=Coalesce(Sum("quantity_input", filter=in_q), _ZERO),
            out_qty=Coalesce(Sum("quantity_input", filter=out_q), _ZERO),
            in_amount=Coalesce(Sum(_AMOUNT, filter=in_q), _ZERO),
            last_in=Max("occurred_at", filter=in_q),
            last_out=Max("occurred_at", filter=out_q),
        )
        .order_by("managed_item__department__name", "managed_item__item__name")
    )

    result = []
    for r in rows:
        in_qty = r["in_qty"] or Decimal("0")
        out_qty = r["out_qty"] or Decimal("0")
        result.append(
            {
                "department": r["managed_item__department__name"],
                "item_name": r["managed_item__item__name"],
                "specification": r["managed_item__item__specification"] or "",
                "in_qty": in_qty,
                "out_qty": out_qty,
                "net": in_qty - out_qty,
                "in_amount": r["in_amount"] or Decimal("0"),
                "last_in": r["last_in"],
                "last_out": r["last_out"],
            }
        )
    return result
