"""inventory 권한 함수. (TECH_SPEC §5 / TASK 07)

여기서는 순수 권한 판정만 한다. 현재고 음수 검증 등 도메인 규칙은 service 에서 처리한다.
"""

from django.utils import timezone

from accounts.models import Role
from accounts.permissions import has_role_at_least, is_manager_or_above
from inventory.models import (
    OUT_TRANSACTION_TYPES,
    TransactionStatus,
    TransactionType,
)

# 취소 가능한 "일반 거래" 유형 (INITIAL_COUNT / ADJUSTMENT 제외). (PRODUCT_SPEC §6.3)
CANCELABLE_TRANSACTION_TYPES = frozenset(
    {TransactionType.IN, *OUT_TRANSACTION_TYPES}
)


def _is_authenticated(user) -> bool:
    return user is not None and getattr(user, "is_authenticated", False)


def can_access_managed_item(user, managed_item) -> bool:
    """관리품목 접근 권한.

    - MANAGER / ADMIN → 전체
    - STAFF / TEAM_LEADER → 본인 부서만
    """
    if not _is_authenticated(user):
        return False
    if is_manager_or_above(user):
        return True
    return managed_item.department_id == getattr(user, "department_id", None)


def can_cancel_transaction(user, transaction_obj) -> bool:
    """APPROVED 일반 거래 취소 권한. (PRODUCT_SPEC §6.3, §6.5)

    공통 조건:
    - status = APPROVED
    - transaction_type 이 INITIAL_COUNT / ADJUSTMENT 가 아님 (일반 거래만)

    역할별:
    - MANAGER / ADMIN → 전체 부서 (당일 제한 없음)
    - TEAM_LEADER → 본인 부서 + 당일
    - STAFF → 본인이 생성 + 당일
    """
    if not _is_authenticated(user):
        return False

    tx = transaction_obj
    if tx.status != TransactionStatus.APPROVED:
        return False
    if tx.transaction_type not in CANCELABLE_TRANSACTION_TYPES:
        return False

    # MANAGER 이상은 부서/당일 제한 없이 취소 가능
    if is_manager_or_above(user):
        return True

    # STAFF / TEAM_LEADER 는 당일 거래만
    is_today = timezone.localdate(tx.created_at) == timezone.localdate()
    if not is_today:
        return False

    if has_role_at_least(user, Role.TEAM_LEADER):
        # 본인 부서 당일 일반 거래
        return tx.managed_item.department_id == getattr(user, "department_id", None)

    # STAFF: 본인이 생성한 당일 거래
    return tx.created_by_id == user.id
