from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models


class Role(models.TextChoices):
    """운영 화면 권한 역할. (TECH_SPEC §5)

    계층: STAFF < TEAM_LEADER < MANAGER < ADMIN
    """

    STAFF = "STAFF", "STAFF"
    TEAM_LEADER = "TEAM_LEADER", "팀장"
    MANAGER = "MANAGER", "운영진"
    ADMIN = "ADMIN", "관리자"


class UserManager(DjangoUserManager):
    """create_superuser 시 role=ADMIN, is_staff=True, is_superuser=True 강제. (TECH_SPEC §4)"""

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields["role"] = Role.ADMIN
        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """직원 계정. accounts.User(AbstractUser). (TECH_SPEC §4)

    AbstractUser 상속 필드(username, password, email, first_name, last_name,
    is_active, is_staff, is_superuser, date_joined, last_login)는 재정의하지 않는다.
    """

    name = models.CharField(max_length=100, blank=True, default="")
    department = models.ForeignKey(
        "core.Department",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STAFF)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # username 만으로 사용자 생성 (email 강제하지 않음). (TECH_SPEC §4)
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "사용자"
        verbose_name_plural = "사용자"

    def __str__(self):
        return self.name or self.username
