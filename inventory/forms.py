"""inventory Form. (TECH_SPEC §12 / TASK 13)

원칙:
- 생성 Form 은 user-aware Form 으로 구현하고, managed_item queryset 을
  get_accessible_managed_items(user) 로 제한한다.
- 모든 Form 은 forms.Form 이다 (ModelForm 아님). 따라서 Form.save() 로
  StockTransaction 을 직접 저장하지 않는다. cleaned_data 는 View 에서
  services.py 의 함수로 전달한다. (TECH_SPEC §0, §13)
"""

from django import forms
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
    get_accessible_managed_items,
    get_pending_transactions,
)

# 출고 유형 선택값 (OUT 계열만)
OUT_TYPE_CHOICES = [
    (TransactionType.OUT_USE.value, TransactionType.OUT_USE.label),
    (TransactionType.OUT_DISCARD.value, TransactionType.OUT_DISCARD.label),
    (TransactionType.OUT_LOST.value, TransactionType.OUT_LOST.label),
    (TransactionType.OUT_GIFT.value, TransactionType.OUT_GIFT.label),
    (TransactionType.OUT_OTHER.value, TransactionType.OUT_OTHER.label),
]


# ---------------------------------------------------------------------------
# 공통 mixin
# ---------------------------------------------------------------------------
class OccurredAtMixin(forms.Form):
    """occurred_at 기본값 = 현재 시각, 미래 금지."""

    occurred_at = forms.DateTimeField(
        label="발생일시",
        initial=timezone.now,
        required=True,
    )

    def clean_occurred_at(self):
        value = self.cleaned_data.get("occurred_at")
        if value and value > timezone.now():
            raise forms.ValidationError("발생일시는 미래일 수 없습니다.")
        return value


class AccessibleManagedItemMixin:
    """managed_item queryset 을 사용자 접근 범위(활성)로 제한한다."""

    def _set_managed_item_queryset(self, user):
        qs = get_accessible_managed_items(user).filter(is_active=True)
        self.fields["managed_item"].queryset = qs


# ---------------------------------------------------------------------------
# 생성 Form (user-aware)
# ---------------------------------------------------------------------------
class StockInForm(AccessibleManagedItemMixin, OccurredAtMixin, forms.Form):
    """입고 등록 Form. (PRODUCT_SPEC §10.6)"""

    managed_item = forms.ModelChoiceField(
        label="관리품목", queryset=StockTransaction.objects.none()
    )
    quantity = forms.DecimalField(
        label="입고수량", max_digits=12, decimal_places=3
    )
    supplier = forms.ModelChoiceField(
        label="공급업체",
        queryset=Supplier.objects.filter(is_active=True),
        required=False,
    )
    unit_price = forms.DecimalField(
        label="입고단가", max_digits=12, decimal_places=2, required=False
    )
    expiration_date = forms.DateField(label="유통기한", required=False)
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
        self._set_managed_item_queryset(user)
        # STAFF 에게는 unit_price 필드를 노출하지 않는다. (PRODUCT_SPEC §10.6)
        if not has_role_at_least(user, Role.TEAM_LEADER):
            self.fields.pop("unit_price", None)

    def clean_quantity(self):
        qty = self.cleaned_data.get("quantity")
        if qty is None or qty <= 0:
            raise forms.ValidationError("입고수량은 0보다 커야 합니다.")
        return qty


class StockOutForm(AccessibleManagedItemMixin, OccurredAtMixin, forms.Form):
    """출고 등록 Form. (PRODUCT_SPEC §10.7)"""

    managed_item = forms.ModelChoiceField(
        label="관리품목", queryset=StockTransaction.objects.none()
    )
    transaction_type = forms.ChoiceField(label="출고 유형", choices=OUT_TYPE_CHOICES)
    quantity = forms.DecimalField(
        label="출고수량", max_digits=12, decimal_places=3
    )
    memo = forms.CharField(
        label="메모", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    field_order = ["managed_item", "transaction_type", "quantity", "occurred_at", "memo"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self._set_managed_item_queryset(user)

    def clean_quantity(self):
        qty = self.cleaned_data.get("quantity")
        if qty is None or qty <= 0:
            raise forms.ValidationError("출고수량은 0보다 커야 합니다.")
        return qty


class AdjustmentRequestForm(AccessibleManagedItemMixin, OccurredAtMixin, forms.Form):
    """실사조정 요청 Form. (PRODUCT_SPEC §10.10)"""

    managed_item = forms.ModelChoiceField(
        label="관리품목", queryset=StockTransaction.objects.none()
    )
    actual_quantity = forms.DecimalField(
        label="실제 수량", max_digits=12, decimal_places=3
    )
    reason = forms.CharField(label="조정 사유", max_length=255)
    memo = forms.CharField(
        label="메모", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    field_order = ["managed_item", "actual_quantity", "occurred_at", "reason", "memo"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self._set_managed_item_queryset(user)

    def clean_actual_quantity(self):
        qty = self.cleaned_data.get("actual_quantity")
        if qty is None or qty < 0:
            raise forms.ValidationError("실제 수량은 0 이상이어야 합니다.")
        return qty


class InitialCountForm(AccessibleManagedItemMixin, OccurredAtMixin, forms.Form):
    """초기재고 입력 Form. (PRODUCT_SPEC §10.11)"""

    managed_item = forms.ModelChoiceField(
        label="관리품목", queryset=StockTransaction.objects.none()
    )
    quantity = forms.DecimalField(
        label="초기재고 수량", max_digits=12, decimal_places=3
    )
    memo = forms.CharField(
        label="메모", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    field_order = ["managed_item", "quantity", "occurred_at", "memo"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self._set_managed_item_queryset(user)

    def clean_quantity(self):
        qty = self.cleaned_data.get("quantity")
        if qty is None or qty < 0:
            raise forms.ValidationError("초기재고 수량은 0 이상이어야 합니다.")
        return qty


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
    """거래 이력 필터. (PRODUCT_SPEC §10.14)"""

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
