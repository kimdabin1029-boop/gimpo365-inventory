from django.contrib import admin

from inventory.models import Item, ManagedItem, StockTransaction, Supplier


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
