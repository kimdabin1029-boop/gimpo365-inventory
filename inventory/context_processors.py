"""좌측 퀵메뉴(사이드바)용 컨텍스트. (v0.1.3)

권한 체계를 변경하지 않고, 기존 권한 헬퍼를 템플릿에서 쓰기 위한 표시 전용 플래그만 제공한다.
- nav_is_manager : MANAGER 이상 (승인대기 메뉴 노출 여부)
- nav_can_adjust : TEAM_LEADER 이상 (실사조정 메뉴 노출 여부)
"""

from accounts.models import Role
from accounts.permissions import has_role_at_least, is_manager_or_above


def nav_flags(request):
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return {"nav_is_manager": False, "nav_can_adjust": False}
    return {
        "nav_is_manager": is_manager_or_above(user),
        "nav_can_adjust": has_role_at_least(user, Role.TEAM_LEADER),
    }
