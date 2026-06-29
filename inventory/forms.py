"""inventory Form. (TECH_SPEC §12 / TASK 13)

원칙:
- 생성 Form 은 user-aware Form 으로 구현하고, managed_item queryset 을
  get_accessible_managed_items(user) 로 제한한다.
- 모든 Form 은 forms.Form 이다 (ModelForm 아님). 따라서 Form.save() 로
  StockTransaction 을 직접 저장하지 않는다. cleaned_data 는 View 에서
  services.py 의 함수로 전달한다. (TECH_SPEC §0, §13)
"""

from datetime import datetime, time

from django import forms
from django.db.models import Exists, OuterRef
from django.utils import timezone

from accounts.models import Role
from accounts.permissions import has_role_at_least
from core.models import Department
from inventory.models import (
    ItemCategory,
    StockTransaction,
    Supplier,
    TransactionStatus,
    TransactionType,
)
from inventory.selectors import (
    get_managed_items_with_current_stock,
    get_pending_transactions,
)
from inventory.templatetags.inventory_extras import qty

# 출고 유형 선택값 (OUT 계열만)
OUT_TYPE_CHOICES = [
    (TransactionType.OUT_USE.value, TransactionType.OUT_USE.label),
    (TransactionType.OUT_DISCARD.value, TransactionType.OUT_DISCARD.label),
    (TransactionType.OUT_LOST.value, TransactionType.OUT_LOST.label),
    (TransactionType.OUT_GIFT.value, TransactionType.OUT_GIFT.label),
    (TransactionType.OUT_OTHER.value, TransactionType.OUT_OTHER.label),
]

# 실사조정 사유 고정 선택값 (v0.1.1) — "기타" 선택 시 메모에 상세 입력
ADJUSTMENT_REASON_CHOICES = [
    ("실물 재고 부족", "실물 재고 부족"),
    ("실물 재고 초과", "실물 재고 초과"),
    ("이전 입출고 누락", "이전 입출고 누락"),
    ("폐기/분실 기록 누락", "폐기/분실 기록 누락"),
    ("초기재고 입력 오류", "초기재고 입력 오류"),
    ("기타", "기타"),
]


def _qty_widget(*, allow_zero: bool):
    """수량 입력 위젯. 상하 버튼 step=1 (실무 정수 단위). 소수 직접 입력은 가능."""
    attrs = {"step": "1"}
    if allow_zero:
        attrs["min"] = "0"
    return forms.NumberInput(attrs=attrs)


def _date_widget():
    return forms.DateInput(attrs={"type": "date"})


class ManagedItemSelect(forms.Select):
    """관리품목 <select>. 각 옵션에 현재고/최소재고/보관장소/단위 data-* 부여. (v0.1.1)

    선택 시 화면의 정보 패널(현재고 등) 표시 및 출고 후 예상 재고 계산에 사용된다.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stock_map = {}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs
        )
        pk = getattr(value, "value", value)
        data = self.stock_map.get(str(pk))
        if data:
            option["attrs"].update(
                {
                    "data-stock": data["stock"],
                    "data-min": data["min"],
                    "data-loc": data["loc"],
                    "data-unit": data["unit"],
                    "data-name": data["name"],
                    "data-dept": data["dept"],
                    # mode: 승인 초기재고 없으면 "initial"(최초 재고 입력), 있으면 "adjustment"
                    "data-mode": data["mode"],
                    # 기본 공급업체(있으면) → 입고 화면에서 공급업체 초기값 자동 선택용 (v0.1.2)
                    "data-supplier": data["supplier"],
                    "data-supplier-name": data["supplier_name"],
                }
            )
        return option


class ManagedItemChoiceField(forms.ModelChoiceField):
    """관리품목 선택지 라벨에 품목명/규격/부서/단위(+현재고) 노출. (v0.1.1)"""

    widget = ManagedItemSelect

    def label_from_instance(self, obj):
        name = obj.item.name
        spec = (obj.item.specification or "").strip()
        head = f"{name} — {spec}" if spec else name
        unit = obj.get_unit_display()
        label = f"{head} / {obj.department.name} / {unit}"
        current = getattr(obj, "current_stock", None)
        if current is not None:
            label += f" / 현재고 {qty(current)} {unit}"
        return label


# ---------------------------------------------------------------------------
# 공통 helper (거래일자 / 관리품목 queryset)
# ---------------------------------------------------------------------------
def _trade_date_field(label):
    """거래일자(날짜 선택) 필드. 기본값 오늘, 시간 입력은 숨김."""
    return forms.DateField(label=label, initial=timezone.localdate, widget=_date_widget())


def _clean_trade_date(value, label):
    """거래일자(date) → service 용 datetime 변환. 미래 금지.

    오늘=현재 시각 / 과거=해당 일자 00:00(로컬). service.occurred_at(datetime) 구조 유지.
    """
    if value is None:
        return None
    today = timezone.localdate()
    if value > today:
        raise forms.ValidationError(f"{label}는 미래일 수 없습니다.")
    if value == today:
        return timezone.now()
    return timezone.make_aware(datetime.combine(value, time.min))


def _set_managed_item_with_stock(form, user):
    """managed_item queryset 을 권한 범위(활성)로 제한 + 옵션에 현재고 data 부여.

    user-aware 유지: get_accessible_managed_items 범위(권한 밖 미노출)를 그대로 따른다.
    """
    qs = get_managed_items_with_current_stock(user).filter(is_active=True)
    # 각 관리품목에 승인된 최초 재고(INITIAL_COUNT) 존재 여부 주석 (N+1 방지)
    qs = qs.annotate(
        _has_initial=Exists(
            StockTransaction.objects.filter(
                managed_item=OuterRef("pk"),
                transaction_type=TransactionType.INITIAL_COUNT,
                status=TransactionStatus.APPROVED,
            )
        )
    )
    field = form.fields["managed_item"]
    field.queryset = qs
    stock_map = {}
    for mi in qs:
        stock_map[str(mi.pk)] = {
            "stock": qty(mi.current_stock),
            "min": qty(mi.minimum_stock),
            "loc": mi.storage_location or "-",
            "unit": mi.get_unit_display(),
            "name": mi.item.name,
            "dept": mi.department.name,
            "mode": "adjustment" if mi._has_initial else "initial",
            # 기본 공급업체 pk/이름 (없으면 빈 문자열) — 입고 화면 초기값 자동 선택용
            "supplier": str(mi.default_supplier_id or ""),
            "supplier_name": mi.default_supplier.name if mi.default_supplier_id else "",
        }
    field.widget.stock_map = stock_map


# ---------------------------------------------------------------------------
# 생성 Form (user-aware)
# ---------------------------------------------------------------------------
class StockInForm(forms.Form):
    """입고 등록 Form. 입고일자(날짜) 입력. (PRODUCT_SPEC §10.6)"""

    managed_item = ManagedItemChoiceField(
        label="관리품목", queryset=StockTransaction.objects.none()
    )
    quantity = forms.DecimalField(
        label="입고수량", max_digits=12, decimal_places=3, widget=_qty_widget(allow_zero=False)
    )
    occurred_at = _trade_date_field("입고일자")
    supplier = forms.ModelChoiceField(
        label="공급업체",
        queryset=Supplier.objects.filter(is_active=True),
        required=False,
    )
    unit_price = forms.DecimalField(
        label="입고단가", max_digits=12, decimal_places=2, required=False
    )
    expiration_date = forms.DateField(
        label="유통기한", required=False, widget=_date_widget()
    )
    memo = forms.CharField(
        label="메모", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    field_order = [
        "managed_item",
        "quantity",
        "occurred_at",
        "supplier",
        "unit_price",
        "expiration_date",
        "memo",
    ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        _set_managed_item_with_stock(self, user)
        # STAFF 에게는 unit_price 필드를 노출하지 않는다. (PRODUCT_SPEC §10.6)
        if not has_role_at_least(user, Role.TEAM_LEADER):
            self.fields.pop("unit_price", None)

    def clean_quantity(self):
        value = self.cleaned_data.get("quantity")
        if value is None or value <= 0:
            raise forms.ValidationError("입고수량은 0보다 커야 합니다.")
        return value

    def clean_occurred_at(self):
        return _clean_trade_date(self.cleaned_data.get("occurred_at"), "입고일자")


class StockOutForm(forms.Form):
    """출고 등록 Form. 출고일자(날짜) 입력. (PRODUCT_SPEC §10.7)"""

    managed_item = ManagedItemChoiceField(
        label="관리품목", queryset=StockTransaction.objects.none()
    )
    transaction_type = forms.ChoiceField(label="출고 유형", choices=OUT_TYPE_CHOICES)
    quantity = forms.DecimalField(
        label="출고수량", max_digits=12, decimal_places=3, widget=_qty_widget(allow_zero=False)
    )
    occurred_at = _trade_date_field("출고일자")
    memo = forms.CharField(
        label="메모", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    field_order = ["managed_item", "transaction_type", "quantity", "occurred_at", "memo"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        _set_managed_item_with_stock(self, user)

    def clean_quantity(self):
        value = self.cleaned_data.get("quantity")
        if value is None or value <= 0:
            raise forms.ValidationError("출고수량은 0보다 커야 합니다.")
        return value

    def clean_occurred_at(self):
        return _clean_trade_date(self.cleaned_data.get("occurred_at"), "출고일자")


class AdjustmentRequestForm(forms.Form):
    """실사조정 요청 Form (최초 재고 입력 / 실사조정 통합). (v0.1.1 / PRODUCT_SPEC §10.10)

    선택한 관리품목에 승인된 최초 재고가 없으면 '최초 재고 입력'(INITIAL_COUNT),
    있으면 '실사조정'(ADJUSTMENT) 으로 처리한다. 실사조정 모드에서만 reason 이 필수다.
    """

    managed_item = ManagedItemChoiceField(
        label="관리품목", queryset=StockTransaction.objects.none()
    )
    actual_quantity = forms.DecimalField(
        label="실제 수량", max_digits=12, decimal_places=3, widget=_qty_widget(allow_zero=True)
    )
    occurred_at = _trade_date_field("기준일자")
    reason = forms.ChoiceField(
        label="조정 사유",
        choices=ADJUSTMENT_REASON_CHOICES,
        required=False,  # 최초 재고 입력 모드에서는 불필요 → clean 에서 조건부 검증
        help_text="실사조정 시 사유를 선택하세요. ‘기타’는 상세 내용을 메모에 입력합니다.",
    )
    memo = forms.CharField(
        label="메모", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    field_order = ["managed_item", "actual_quantity", "occurred_at", "reason", "memo"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        _set_managed_item_with_stock(self, user)

    def clean_actual_quantity(self):
        value = self.cleaned_data.get("actual_quantity")
        if value is None or value < 0:
            raise forms.ValidationError("실제 수량은 0 이상이어야 합니다.")
        return value

    def clean_occurred_at(self):
        return _clean_trade_date(self.cleaned_data.get("occurred_at"), "기준일자")

    def clean(self):
        cleaned = super().clean()
        mi = cleaned.get("managed_item")
        # 실사조정 모드(승인된 최초 재고 존재)일 때만 사유 필수
        if mi is not None and getattr(mi, "_has_initial", None) is None:
            from inventory.selectors import has_approved_initial_count

            is_adjustment = has_approved_initial_count(mi)
        else:
            is_adjustment = bool(getattr(mi, "_has_initial", False)) if mi else False
        if is_adjustment and not (cleaned.get("reason") or "").strip():
            self.add_error("reason", "실사조정 시 조정 사유는 필수입니다.")
        return cleaned


class InitialCountForm(forms.Form):
    """초기재고 입력 Form. 기준일자(날짜) 입력. (PRODUCT_SPEC §10.11)"""

    managed_item = ManagedItemChoiceField(
        label="관리품목", queryset=StockTransaction.objects.none()
    )
    quantity = forms.DecimalField(
        label="초기재고 수량", max_digits=12, decimal_places=3, widget=_qty_widget(allow_zero=True)
    )
    occurred_at = _trade_date_field("기준일자")
    memo = forms.CharField(
        label="메모", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    field_order = ["managed_item", "quantity", "occurred_at", "memo"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        _set_managed_item_with_stock(self, user)

    def clean_quantity(self):
        value = self.cleaned_data.get("quantity")
        if value is None or value < 0:
            raise forms.ValidationError("초기재고 수량은 0 이상이어야 합니다.")
        return value

    def clean_occurred_at(self):
        return _clean_trade_date(self.cleaned_data.get("occurred_at"), "기준일자")


# ---------------------------------------------------------------------------
# 상태 변경 Form
# ---------------------------------------------------------------------------
class ApproveTransactionForm(forms.Form):
    review_note = forms.CharField(
        label="검토 메모",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class RejectTransactionForm(forms.Form):
    # 반려 사유 필수
    review_note = forms.CharField(
        label="반려 사유", widget=forms.Textarea(attrs={"rows": 2})
    )


class WithdrawPendingTransactionForm(forms.Form):
    # 철회 사유 필수
    cancel_reason = forms.CharField(
        label="철회 사유", widget=forms.Textarea(attrs={"rows": 2})
    )


class CancelTransactionForm(forms.Form):
    # 취소 사유 필수
    cancel_reason = forms.CharField(
        label="취소 사유", widget=forms.Textarea(attrs={"rows": 2})
    )


class BulkApproveInitialCountsForm(forms.Form):
    """승인 큐에서 선택한 PENDING INITIAL_COUNT 들의 일괄 승인."""

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            qs = get_pending_transactions(user).filter(
                transaction_type=TransactionType.INITIAL_COUNT
            )
        else:
            qs = StockTransaction.objects.none()
        self.fields["selected"] = forms.ModelMultipleChoiceField(
            label="초기재고 선택",
            queryset=qs,
            widget=forms.CheckboxSelectMultiple,
        )


# ---------------------------------------------------------------------------
# 필터 Form (조회 화면용)
# ---------------------------------------------------------------------------
class StockFilterForm(forms.Form):
    """현재고 조회 필터. (PRODUCT_SPEC §10.8)"""

    department = forms.ModelChoiceField(
        label="부서",
        queryset=Department.objects.filter(active_for_inventory=True),
        required=False,
    )
    category = forms.ChoiceField(
        label="분류",
        choices=[("", "전체")] + list(ItemCategory.choices),
        required=False,
    )
    storage_location = forms.CharField(label="보관장소", required=False)
    low_stock = forms.BooleanField(label="최소재고 이하만", required=False)
    is_active = forms.BooleanField(label="활성만", required=False)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # STAFF / TEAM_LEADER 는 부서 필터를 본인 부서로 제한
        if user is not None and not has_role_at_least(user, Role.MANAGER):
            dept_id = getattr(user, "department_id", None)
            self.fields["department"].queryset = Department.objects.filter(
                pk=dept_id
            )


class TransactionFilterForm(forms.Form):
    """거래 이력 필터. (PRODUCT_SPEC §10.14)

    기간 필터는 거래일자(occurred_at) 기준. 기본값(파라미터 없음)은 오늘~오늘.
    """

    date_from = forms.DateField(
        label="거래일자(부터)", required=False, widget=_date_widget()
    )
    date_to = forms.DateField(
        label="거래일자(까지)", required=False, widget=_date_widget()
    )
    department = forms.ModelChoiceField(
        label="부서",
        queryset=Department.objects.filter(active_for_inventory=True),
        required=False,
    )
    transaction_type = forms.ChoiceField(
        label="거래유형",
        choices=[("", "전체")] + list(TransactionType.choices),
        required=False,
    )
    status = forms.ChoiceField(
        label="상태",
        choices=[("", "전체")] + list(TransactionStatus.choices),
        required=False,
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None and not has_role_at_least(user, Role.MANAGER):
            dept_id = getattr(user, "department_id", None)
            self.fields["department"].queryset = Department.objects.filter(
                pk=dept_id
            )


class PendingTransactionFilterForm(forms.Form):
    """승인 큐 필터. (PRODUCT_SPEC §10.12)"""

    department = forms.ModelChoiceField(
        label="부서",
        queryset=Department.objects.filter(active_for_inventory=True),
        required=False,
    )
    transaction_type = forms.ChoiceField(
        label="거래유형",
        choices=[
            ("", "전체"),
            (TransactionType.INITIAL_COUNT.value, TransactionType.INITIAL_COUNT.label),
            (TransactionType.ADJUSTMENT.value, TransactionType.ADJUSTMENT.label),
        ],
        required=False,
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None and not has_role_at_least(user, Role.MANAGER):
            dept_id = getattr(user, "department_id", None)
            self.fields["department"].queryset = Department.objects.filter(
                pk=dept_id
            )
