"""공통 테스트 fixture / factory. (TASKS TASK 03)

테스트에서 재사용할 기본 부서·사용자 데이터를 생성한다.
Supplier / Item / ManagedItem / StockTransaction factory 는 이후 TASK에서 확장한다.

주의: 이 모듈은 test*.py 패턴이 아니므로 테스트 러너가 직접 수집하지 않는다.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import Role
from core.models import Department
from inventory.models import (
    Item,
    ItemCategory,
    ManagedItem,
    StockTransaction,
    Supplier,
    TransactionStatus,
    TransactionType,
    Unit,
)

User = get_user_model()

DEFAULT_PASSWORD = "pw12345!"


# ---------------------------------------------------------------------------
# Department factory
# ---------------------------------------------------------------------------
def create_department(name, *, active_for_inventory=True, is_active=True, **kwargs):
    return Department.objects.create(
        name=name,
        active_for_inventory=active_for_inventory,
        is_active=is_active,
        **kwargs,
    )


def create_default_departments():
    """기본 부서 fixture. (TASK 03)

    피부실/치료실 = 재고관리 대상, 탕전실 = 제외(active_for_inventory=False)
    """
    return {
        "skin": create_department("피부실", active_for_inventory=True),
        "treatment": create_department("치료실", active_for_inventory=True),
        "decoction": create_department("탕전실", active_for_inventory=False),
    }


# ---------------------------------------------------------------------------
# User factory
# ---------------------------------------------------------------------------
def create_user(
    username,
    *,
    role=Role.STAFF,
    department=None,
    password=DEFAULT_PASSWORD,
    **kwargs,
):
    return User.objects.create_user(
        username=username,
        password=password,
        role=role,
        department=department,
        **kwargs,
    )


def create_default_users(departments):
    """기본 사용자 fixture. (TASK 03)

    - staff_skin: STAFF, 피부실
    - team_leader_skin: TEAM_LEADER, 피부실
    - staff_treatment: STAFF, 치료실
    - manager: MANAGER, is_staff=False, is_superuser=False
    - admin: ADMIN, is_staff=True, is_superuser=True
    """
    skin = departments["skin"]
    treatment = departments["treatment"]
    return {
        "staff_skin": create_user("staff_skin", role=Role.STAFF, department=skin),
        "team_leader_skin": create_user(
            "team_leader_skin", role=Role.TEAM_LEADER, department=skin
        ),
        "staff_treatment": create_user(
            "staff_treatment", role=Role.STAFF, department=treatment
        ),
        "manager": create_user(
            "manager",
            role=Role.MANAGER,
            department=None,
            is_staff=False,
            is_superuser=False,
        ),
        "admin": create_user(
            "admin",
            role=Role.ADMIN,
            department=None,
            is_staff=True,
            is_superuser=True,
        ),
    }


# ---------------------------------------------------------------------------
# Supplier / Item / ManagedItem factory (TASK 04)
# ---------------------------------------------------------------------------
def create_supplier(name="기본공급사", **kwargs):
    return Supplier.objects.create(name=name, **kwargs)


def create_item(name, *, category=ItemCategory.GENERAL_SUPPLY, **kwargs):
    return Item.objects.create(name=name, category=category, **kwargs)


def create_managed_item(
    *,
    item,
    department,
    unit=Unit.EA,
    minimum_stock=0,
    default_supplier=None,
    **kwargs,
):
    return ManagedItem.objects.create(
        item=item,
        department=department,
        unit=unit,
        minimum_stock=minimum_stock,
        default_supplier=default_supplier,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# StockTransaction factory (TASK 05)
# 주의: 이 직접 생성은 테스트 fixture 전용이다. application code 에서는 금지. (TASKS §0)
# ---------------------------------------------------------------------------
def create_stock_transaction(
    *,
    managed_item,
    transaction_type,
    created_by,
    status=TransactionStatus.APPROVED,
    quantity_input=0,
    quantity_delta=0,
    **kwargs,
):
    return StockTransaction.objects.create(
        managed_item=managed_item,
        transaction_type=transaction_type,
        status=status,
        quantity_input=quantity_input,
        quantity_delta=quantity_delta,
        created_by=created_by,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Base TestCase
# ---------------------------------------------------------------------------
class BaseFixtureTestCase(TestCase):
    """기본 부서/사용자 fixture 를 갖춘 베이스 테스트 케이스.

    이후 모든 TASK 의 테스트는 이 클래스를 상속해 공통 데이터를 재사용한다.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.departments = create_default_departments()
        cls.users = create_default_users(cls.departments)

        # 편의 접근자
        cls.dept_skin = cls.departments["skin"]
        cls.dept_treatment = cls.departments["treatment"]
        cls.dept_decoction = cls.departments["decoction"]

        cls.staff_skin = cls.users["staff_skin"]
        cls.team_leader_skin = cls.users["team_leader_skin"]
        cls.staff_treatment = cls.users["staff_treatment"]
        cls.manager = cls.users["manager"]
        cls.admin = cls.users["admin"]
