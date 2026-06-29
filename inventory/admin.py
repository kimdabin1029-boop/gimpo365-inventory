from django import forms
from django.contrib import admin
from django.utils.html import format_html, format_html_join

from inventory.models import (
    Item,
    ManagedItem,
    Order,
    OrderItem,
    StockTransaction,
    Supplier,
)


class DatalistTextInput(forms.TextInput):
    """기존 입력값을 <datalist> 자동완성으로 제공하는 TextInput. (v0.1.1, 모델 변경 없음)

    storage_location 오타를 줄이기 위한 최소 대응. StorageLocation 모델은 신설하지 않는다.
    """

    def __init__(self, *args, options=(), list_id="storage-location-list", **kwargs):
        self._options = list(options)
        self._list_id = list_id
        attrs = kwargs.pop("attrs", {}) or {}
        attrs.setdefault("list", list_id)
        super().__init__(*args, attrs=attrs, **kwargs)

    def render(self, name, value, attrs=None, renderer=None):
        html = super().render(name, value, attrs=attrs, renderer=renderer)
        options = format_html_join(
            "", '<option value="{}"></option>', ((o,) for o in self._options)
        )
        datalist = format_html('<datalist id="{}">{}</datalist>', self._list_id, options)
        return html + datalist


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ["name", "phone", "manager_name", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name"]


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "specification", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["name"]


@admin.register(ManagedItem)
class ManagedItemAdmin(admin.ModelAdmin):
    list_display = [
        "item",
        "department",
        "unit",
        "minimum_stock",
        "default_supplier",
        "is_active",
    ]
    list_filter = ["department", "is_active", "unit"]
    search_fields = ["item__name"]
    autocomplete_fields = ["item", "department", "default_supplier"]
    # 운영 개시 후 unit 변경 금지는 ManagedItem.clean() 에서 검증되며,
    # Admin ModelForm 저장 시 full_clean 을 통해 동일하게 차단된다. (TECH_SPEC §6.4)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "storage_location":
            # 기존에 입력된 보관장소 값을 datalist 자동완성으로 제공 (오타 감소, 모델 변경 없음)
            values = (
                ManagedItem.objects.exclude(storage_location="")
                .order_by("storage_location")
                .values_list("storage_location", flat=True)
                .distinct()
            )
            field.widget = DatalistTextInput(options=values)
        return field


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    """재고 거래 원장. 조회 중심. (TECH_SPEC §14 / §0)

    - add 금지 / delete 금지 (원장 생성·삭제는 service 로만)
    - 핵심 필드(managed_item / status / quantity / 감사 필드)는 readonly
    """

    list_display = [
        "id",
        "managed_item",
        "transaction_type",
        "status",
        "quantity_input",
        "quantity_delta",
        "created_by",
        "created_at",
    ]
    list_filter = ["status", "transaction_type"]
    search_fields = ["managed_item__item__name"]

    readonly_fields = [
        "managed_item",
        "transaction_type",
        "status",
        "quantity_input",
        "quantity_delta",
        "expected_quantity",
        "actual_quantity",
        "occurred_at",
        "created_by",
        "approved_by",
        "approved_at",
        "supplier",
        "unit_price",
        "expiration_date",
        "canceled_by",
        "canceled_at",
        "created_at",
        "updated_at",
    ]

    def has_add_permission(self, request):
        # Admin 에서 거래 원장 추가 금지 (TECH_SPEC §0)
        return False

    def has_delete_permission(self, request, obj=None):
        # Admin 에서 거래 원장 삭제 금지 (TECH_SPEC §0)
        return False


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ["managed_item", "quantity", "memo"]
    readonly_fields = ["managed_item", "quantity", "memo"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """주문 조회 중심. 주문 생성은 장바구니 → confirm_order service 로만 한다. (v0.2.0)

    - add 금지 (internal_order_no 자동생성/공급업체별 분리 로직을 우회하지 않도록)
    - 상태/감사 필드는 readonly (상태 변경은 order_services 로만)
    """

    list_display = [
        "internal_order_no", "external_order_no", "supplier",
        "ordered_by", "order_date", "status",
    ]
    list_filter = ["status", "supplier"]
    search_fields = ["internal_order_no", "external_order_no"]
    inlines = [OrderItemInline]
    readonly_fields = [
        "internal_order_no", "external_order_no", "supplier", "ordered_by",
        "order_date", "ordered_at", "status", "memo",
        "canceled_by", "canceled_at", "received_by", "received_at",
        "created_at", "updated_at",
    ]

    def has_add_permission(self, request):
        return False
