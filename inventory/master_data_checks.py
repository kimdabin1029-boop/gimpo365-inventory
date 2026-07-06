"""기준정보 점검 로직 (읽기 전용, v0.2.5).

command / 관리자 웹 화면 / 기준정보 엑셀이 모두 이 모듈을 재사용해 동일 기준으로 점검한다.

원칙:
- 조회/판정만 한다. 데이터 생성/수정/삭제 없음.
- 최초재고 기준은 기존 원칙(승인된 INITIAL_COUNT 존재 여부)을 따른다.
- 현재고는 APPROVED 거래 합계(주석)로만 계산한다. (저장 필드 없음)
"""

from decimal import Decimal

from django.db.models import Exists, OuterRef

from inventory.models import (
    Item,
    ManagedItem,
    StockTransaction,
    Supplier,
    TransactionStatus,
    TransactionType,
)
from inventory.selectors import _annotate_current_stock

WARNING = "경고"
CHECK = "확인필요"


def _approved_initial_count_subquery():
    return StockTransaction.objects.filter(
        managed_item=OuterRef("pk"),
        transaction_type=TransactionType.INITIAL_COUNT,
        status=TransactionStatus.APPROVED,
    )


def _base_active_mi():
    return ManagedItem.objects.select_related(
        "item", "department", "default_supplier"
    ).filter(is_active=True)


def run_master_data_checks():
    """기준정보 점검 결과를 구조화해서 돌려준다.

    반환:
      {
        active_count, warning_count, check_count, no_initial_count, normal_count,
        sections: [{key,title,severity,message,recommend,kind,items,count}],
        findings: [{section,severity,dept,item_name,message,recommend,mi_id}],
      }
    """
    active = _base_active_mi()
    ic = _approved_initial_count_subquery()

    sections = []

    def add(key, title, severity, message, recommend, qs, kind="mi"):
        items = list(qs)
        sections.append(
            {
                "key": key,
                "title": title,
                "severity": severity,
                "message": message,
                "recommend": recommend,
                "kind": kind,
                "items": items,
                "count": len(items),
            }
        )

    add(
        "no_default_supplier", "기본 공급업체 없는 관리품목", WARNING,
        "기본 공급업체가 없습니다", "기본 공급업체를 지정하세요",
        active.filter(default_supplier__isnull=True),
    )
    add(
        "bad_min_stock", "최소재고 미입력/0 이하 관리품목", WARNING,
        "최소재고가 비어있거나 0 이하입니다", "최소재고를 입력하세요",
        active.filter(minimum_stock__lte=0),
    )
    add(
        "no_storage_location", "보관위치 미입력 관리품목", WARNING,
        "보관위치가 없습니다", "보관위치를 입력하세요",
        active.filter(storage_location=""),
    )
    add(
        "insufficient_spec", "규격 미표시 관리품목", CHECK,
        "규격이 표시되지 않았습니다", "필요 시 규격을 보완하세요",
        active.filter(item__specification=""),
    )
    add(
        "inactive_supplier_linked", "비활성 공급업체 연결 관리품목", WARNING,
        "기본 공급업체가 비활성입니다", "활성 공급업체로 변경하세요",
        active.filter(default_supplier__isnull=False, default_supplier__is_active=False),
    )
    add(
        "inactive_item_with_managed_item", "비활성 품목의 관리품목", WARNING,
        "연결된 품목이 비활성입니다", "품목/관리품목 사용 여부를 확인하세요",
        active.filter(item__is_active=False),
    )
    add(
        "active_item_no_managed_item", "활성 품목이나 활성 관리품목 없음", WARNING,
        "활성 관리품목이 없습니다", "관리품목을 등록하거나 품목을 사용중지하세요",
        Item.objects.filter(is_active=True)
        .exclude(managed_items__is_active=True)
        .distinct(),
        kind="item",
    )
    add(
        "no_initial_count", "최초재고 미입력 관리품목", CHECK,
        "최초재고가 입력되지 않았습니다", "운영 시작 전 최초재고 입력/승인 필요",
        active.annotate(_ic=Exists(ic)).filter(_ic=False),
    )

    active_count = active.count()
    warning_sections = [s for s in sections if s["severity"] == WARNING]
    check_sections = [s for s in sections if s["severity"] == CHECK]
    warning_count = sum(s["count"] for s in warning_sections)
    check_count = sum(s["count"] for s in check_sections)
    no_initial_count = next(
        s["count"] for s in sections if s["key"] == "no_initial_count"
    )

    # 경고가 하나라도 걸린 활성 관리품목(중복 제거) → 정상 항목 계산용
    flagged_mi_ids = set()
    for s in warning_sections:
        if s["kind"] == "mi":
            flagged_mi_ids.update(m.pk for m in s["items"])
    normal_count = active_count - len(flagged_mi_ids)

    findings = []
    for s in sections:
        for obj in s["items"]:
            if s["kind"] == "mi":
                findings.append(
                    {
                        "section": s["title"],
                        "severity": s["severity"],
                        "dept": obj.department.name,
                        "item_name": obj.item.name,
                        "message": s["message"],
                        "recommend": s["recommend"],
                        "mi_id": obj.pk,
                    }
                )
            else:  # item 단위
                findings.append(
                    {
                        "section": s["title"],
                        "severity": s["severity"],
                        "dept": "",
                        "item_name": obj.name,
                        "message": s["message"],
                        "recommend": s["recommend"],
                        "mi_id": "",
                    }
                )

    return {
        "active_count": active_count,
        "warning_count": warning_count,
        "check_count": check_count,
        "no_initial_count": no_initial_count,
        "normal_count": normal_count,
        "sections": sections,
        "warning_sections": warning_sections,
        "check_sections": check_sections,
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# 엑셀 시트용 목록 (관리품목/품목/공급업체) — 현재고는 APPROVED 합계 주석
# ---------------------------------------------------------------------------
def _status_by_mi(result):
    """관리품목 pk → 점검상태('경고'/'확인필요'/'정상')."""
    sev = {}
    for f in result["findings"]:
        if not f["mi_id"]:
            continue
        cur = sev.get(f["mi_id"])
        if cur == WARNING:
            continue
        if f["severity"] == WARNING or cur is None:
            sev[f["mi_id"]] = f["severity"]
    return sev


def managed_item_rows(result=None):
    """엑셀 Sheet1(관리품목) 행 데이터. 현재고/최초재고여부/점검상태 포함."""
    if result is None:
        result = run_master_data_checks()
    status_map = _status_by_mi(result)
    ic = _approved_initial_count_subquery()
    qs = (
        _annotate_current_stock(
            ManagedItem.objects.select_related("item", "department", "default_supplier")
        )
        .annotate(_ic=Exists(ic))
        .order_by("department__name", "item__name")
    )
    rows = []
    for mi in qs:
        rows.append(
            {
                "department": mi.department.name,
                "item_name": mi.item.name,
                "specification": mi.item.specification or "",
                "unit": mi.get_unit_display(),
                "is_active": "활성" if mi.is_active else "사용중지",
                "current_stock": mi.current_stock if mi.current_stock is not None else Decimal("0"),
                "minimum_stock": mi.minimum_stock,
                "default_supplier": mi.default_supplier.name if mi.default_supplier_id else "",
                "storage_location": mi.storage_location or "",
                "has_initial": "있음" if mi._ic else "없음",
                "status": status_map.get(mi.pk, "정상") if mi.is_active else "-",
            }
        )
    return rows


def item_rows():
    """엑셀 Sheet2(품목) 행 데이터."""
    qs = Item.objects.order_by("name")
    rows = []
    for it in qs:
        managed_count = it.managed_items.count()
        rows.append(
            {
                "name": it.name,
                "specification": it.specification or "",
                "category": it.get_category_display(),
                "is_active": "활성" if it.is_active else "사용중지",
                "managed_count": managed_count,
            }
        )
    return rows


def supplier_rows():
    """엑셀 Sheet3(공급업체) 행 데이터."""
    qs = Supplier.objects.order_by("name")
    rows = []
    for s in qs:
        default_count = s.managed_items.count()
        rows.append(
            {
                "name": s.name,
                "is_active": "활성" if s.is_active else "사용중지",
                "phone": s.phone or "",
                "memo": s.memo or "",
                "default_count": default_count,
            }
        )
    return rows
