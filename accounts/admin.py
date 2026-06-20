from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """사용자 관리. (TECH_SPEC §14)

    Django Admin 접근 자체가 is_staff=True(=ADMIN)에게만 허용되므로 ADMIN 전용이다.
    재고관리 권한(role/department)과 Django 관리자 권한(is_staff/is_superuser)을
    화면상 그룹으로 분리하고, is_staff 의 라벨/도움말을 명확히 한다. (모델 변경 없음)
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

    # 변경(change) 화면 fieldset 구분
    fieldsets = (
        ("계정 정보", {"fields": ("username", "password")}),
        ("개인 정보", {"fields": ("name", "email")}),
        ("재고관리 권한", {"fields": ("role", "department")}),
        (
            "Django 관리자 권한",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        # first_name/last_name 은 운영상 미사용. 모델 유지하되 접힘 영역으로만 노출.
        ("기타(미사용)", {"classes": ("collapse",), "fields": ("first_name", "last_name")}),
        ("기록", {"fields": ("last_login", "date_joined")}),
    )
    # 추가(add) 화면: username + 비밀번호 + 재고관리 권한
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("재고관리 권한", {"fields": ("name", "role", "department")}),
    )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "is_staff":
            field.label = "Django 관리자 페이지 접근 권한"
            field.help_text = (
                "체크 시 Django 관리자 페이지에 로그인할 수 있습니다. "
                "재고관리의 STAFF 역할과는 별개입니다. 일반 직원에게는 체크하지 않습니다."
            )
        return field
