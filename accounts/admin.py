from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """사용자 관리. (TECH_SPEC §14)

    Django Admin 접근 자체가 is_staff=True(=ADMIN)에게만 허용되므로 ADMIN 전용이다.
    """

    list_display = [
        "username",
        "name",
        "role",
        "department",
        "is_active",
        "is_staff",
    ]
    list_filter = ["role", "is_active", "is_staff"]
    search_fields = ["username", "name"]
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("재고 시스템 정보", {"fields": ("name", "role", "department")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("재고 시스템 정보", {"fields": ("name", "role", "department")}),
    )
