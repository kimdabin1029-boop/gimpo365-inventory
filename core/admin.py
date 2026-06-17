from django.contrib import admin

from core.models import Department


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "active_for_inventory", "updated_at"]
    list_filter = ["is_active", "active_for_inventory"]
    search_fields = ["name"]
