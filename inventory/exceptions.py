"""inventory 도메인 예외. (TECH_SPEC §11 / TASK 07)

service 함수는 실패 시 이 예외들을 발생시키고, View 는 이를 사용자 메시지로 변환한다.
"""


class InventoryError(Exception):
    """inventory 도메인 공통 예외 베이스."""


class PermissionDeniedError(InventoryError):
    """권한 부족."""


class InvalidTransactionStateError(InventoryError):
    """허용되지 않은 거래 상태 / 상태 전이."""


class InsufficientStockError(InventoryError):
    """현재고 부족 (출고/취소 후 현재고 음수)."""


class DuplicateInitialCountError(InventoryError):
    """APPROVED INITIAL_COUNT 중복."""


class InvalidQuantityError(InventoryError):
    """수량 검증 실패."""


class InvalidManagedItemError(InventoryError):
    """관리품목 검증 실패 (비활성, 접근 불가 등)."""
