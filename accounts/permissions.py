"""역할 기반 권한 헬퍼. (TECH_SPEC §5)

role = 우리 운영 화면 권한 (STAFF < TEAM_LEADER < MANAGER < ADMIN)
is_staff / is_superuser = Django Admin 출입증 / 전체 권한 (별개 개념)
"""

from accounts.models import Role

# 역할 점수 (TECH_SPEC §5)
ROLE_RANK = {
    Role.STAFF: 10,
    Role.TEAM_LEADER: 20,
    Role.MANAGER: 30,
    Role.ADMIN: 40,
}


def _rank(role) -> int:
    return ROLE_RANK.get(role, 0)


def has_role_at_least(user, role: str) -> bool:
    """user 의 role 이 주어진 role 이상인지 확인한다."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return _rank(user.role) >= _rank(role)


def is_manager_or_above(user) -> bool:
    return has_role_at_least(user, Role.MANAGER)


def is_admin_role(user) -> bool:
    return has_role_at_least(user, Role.ADMIN)
