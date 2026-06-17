"""재고 거래 service. (TECH_SPEC §11)

원칙:
- 재고 원장(StockTransaction) 변경은 반드시 이 모듈의 service 함수로만 수행한다.
- View/Form/Admin 에서 StockTransaction 을 직접 create/save 하지 않는다. (TECH_SPEC §0)
- 각 service: 권한 검사 → 입력 검증 → (필요 시) row lock + 현재고 재검증 → 원장 기록 → 감사 필드 기록
"""

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from accounts.permissions import is_manager_or_above
from inventory.exceptions import (
    DuplicateInitialCountError,
    InsufficientStockError,
    InvalidManagedItemError,
    InvalidQuantityError,
    InvalidTransactionStateError,
    InventoryError,
    PermissionDeniedError,
)
from inventory.models import (
    OUT_TRANSACTION_TYPES,
    ManagedItem,
    StockTransaction,
    TransactionStatus,
    TransactionType,
)
from inventory.permissions import can_access_managed_item
from inventory.selectors import get_current_stock, has_approved_initial_count


# ---------------------------------------------------------------------------
# 공통 검증 / helper (TASK 08)
# ---------------------------------------------------------------------------
def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise InvalidQuantityError("수량이 올바른 숫자가 아닙니다.")


def _validate_positive_quantity(value) -> Decimal:
    """입고/출고 수량: 0보다 커야 한다."""
    qty = _to_decimal(value)
    if qty <= 0:
        raise InvalidQuantityError("수량은 0보다 커야 합니다.")
    return qty


def _validate_non_negative_quantity(value) -> Decimal:
    """초기재고/실사 수량: 0 이상이어야 한다."""
    qty = _to_decimal(value)
    if qty < 0:
        raise InvalidQuantityError("수량은 0 이상이어야 합니다.")
    return qty


def _validate_occurred_at(occurred_at):
    """발생일시 검증. 기본값은 현재 시각, 미래는 허용하지 않는다. (TECH_SPEC §12)"""
    if occurred_at is None:
        return timezone.now()
    if occurred_at > timezone.now():
        raise InventoryError("발생일시는 미래일 수 없습니다.")
    return occurred_at


def _check_access(user, managed_item):
    if not can_access_managed_item(user, managed_item):
        raise PermissionDeniedError("해당 관리품목에 접근 권한이 없습니다.")


def _ensure_active_managed_item(managed_item):
    if not managed_item.is_active:
        raise InvalidManagedItemError("비활성 관리품목에는 거래를 등록할 수 없습니다.")


def _lock_managed_item(managed_item) -> ManagedItem:
    """ManagedItem row lock. 출고/취소 시 현재고 재검증 직전에 사용. (TECH_SPEC §15.4)

    반드시 transaction.atomic() 안에서 호출한다.
    """
    return ManagedItem.objects.select_for_update().get(pk=managed_item.pk)


def _lock_transaction(transaction_obj) -> StockTransaction:
    """StockTransaction row lock + 최신 상태 재확인. 승인/반려/철회/취소에서 사용."""
    return StockTransaction.objects.select_for_update().get(pk=transaction_obj.pk)


# ---------------------------------------------------------------------------
# 입고 / 출고 service (TASK 09)
# ---------------------------------------------------------------------------
@transaction.atomic
def create_stock_in(
    *,
    user,
    managed_item,
    quantity,
    occurred_at=None,
    supplier=None,
    unit_price=None,
    expiration_date=None,
    memo="",
):
    """입고 등록. STAFF 이상, 즉시 APPROVED, quantity_delta=+quantity. (TECH_SPEC §11)

    supplier 기본값은 ManagedItem.default_supplier.
    unit_price 의 STAFF 제한은 Form 에서 처리한다 (service 는 받은 값을 그대로 저장).
    """
    _check_access(user, managed_item)
    _ensure_active_managed_item(managed_item)
    qty = _validate_positive_quantity(quantity)
    occurred = _validate_occurred_at(occurred_at)

    if supplier is None:
        supplier = managed_item.default_supplier

    return StockTransaction.objects.create(
        managed_item=managed_item,
        transaction_type=TransactionType.IN,
        status=TransactionStatus.APPROVED,
        quantity_input=qty,
        quantity_delta=qty,
        occurred_at=occurred,
        created_by=user,
        supplier=supplier,
        unit_price=unit_price,
        expiration_date=expiration_date,
        memo=memo,
    )


@transaction.atomic
def create_stock_out(
    *,
    user,
    managed_item,
    transaction_type,
    quantity,
    occurred_at=None,
    memo="",
):
    """출고 등록. STAFF 이상, OUT 계열만, 즉시 APPROVED, quantity_delta=-quantity.

    현재고 음수 방지: row lock 후 현재고를 재검증한다. (TECH_SPEC §15.4)
    """
    _check_access(user, managed_item)
    _ensure_active_managed_item(managed_item)

    if transaction_type not in OUT_TRANSACTION_TYPES:
        raise InvalidTransactionStateError("출고 거래 유형이 아닙니다.")

    qty = _validate_positive_quantity(quantity)
    occurred = _validate_occurred_at(occurred_at)

    locked = _lock_managed_item(managed_item)
    current = get_current_stock(locked)
    if current - qty < 0:
        raise InsufficientStockError(
            f"현재고({current})보다 많은 수량({qty})은 출고할 수 없습니다."
        )

    return StockTransaction.objects.create(
        managed_item=locked,
        transaction_type=transaction_type,
        status=TransactionStatus.APPROVED,
        quantity_input=qty,
        quantity_delta=-qty,
        occurred_at=occurred,
        created_by=user,
        memo=memo,
    )


# ---------------------------------------------------------------------------
# 초기재고 / 실사조정 service (TASK 10)
# ---------------------------------------------------------------------------
@transaction.atomic
def request_adjustment(
    *,
    user,
    managed_item,
    actual_quantity,
    reason,
    occurred_at=None,
    memo="",
):
    """실사조정 요청. STAFF 이상, 생성 시 PENDING. (TECH_SPEC §11 / PRODUCT_SPEC §5.4)

    expected_quantity = 요청 시점 현재고
    quantity_delta = actual_quantity - expected_quantity
    reason 필수.
    """
    _check_access(user, managed_item)

    if not reason or not str(reason).strip():
        raise InventoryError("실사조정 사유(reason)는 필수입니다.")

    actual = _validate_non_negative_quantity(actual_quantity)
    occurred = _validate_occurred_at(occurred_at)

    locked = _lock_managed_item(managed_item)
    expected = get_current_stock(locked)
    delta = actual - expected

    return StockTransaction.objects.create(
        managed_item=locked,
        transaction_type=TransactionType.ADJUSTMENT,
        status=TransactionStatus.PENDING,
        quantity_input=actual,
        quantity_delta=delta,
        expected_quantity=expected,
        actual_quantity=actual,
        occurred_at=occurred,
        created_by=user,
        reason=reason,
        memo=memo,
    )


@transaction.atomic
def request_initial_count(
    *,
    user,
    managed_item,
    quantity,
    occurred_at=None,
    memo="",
):
    """초기재고 입력. (TECH_SPEC §11 / PRODUCT_SPEC §5.5, §5.6)

    - STAFF / TEAM_LEADER → PENDING
    - MANAGER / ADMIN → 즉시 APPROVED
    - APPROVED INITIAL_COUNT 가 이미 있으면 차단
    - PENDING INITIAL_COUNT 중복은 허용
    """
    _check_access(user, managed_item)
    qty = _validate_non_negative_quantity(quantity)
    occurred = _validate_occurred_at(occurred_at)

    locked = _lock_managed_item(managed_item)
    if has_approved_initial_count(locked):
        raise DuplicateInitialCountError(
            "이미 승인된 초기재고가 있습니다. 차이는 실사조정(ADJUSTMENT)으로 처리하세요."
        )

    # 정책: MANAGER/ADMIN 이 생성해 즉시 APPROVED 되는 초기재고는
    #   created_by  = 생성자(=승인자) user
    #   approved_by = 동일 user (자가승인 감사 기록)
    #   approved_at = 승인 시각(now)
    # 을 모두 기록한다. (감사 추적성 유지 — 운영 결정 사항)
    if is_manager_or_above(user):
        status = TransactionStatus.APPROVED
        approved_by = user
        approved_at = timezone.now()
    else:
        status = TransactionStatus.PENDING
        approved_by = None
        approved_at = None

    return StockTransaction.objects.create(
        managed_item=locked,
        transaction_type=TransactionType.INITIAL_COUNT,
        status=status,
        quantity_input=qty,
        quantity_delta=qty,
        occurred_at=occurred,
        created_by=user,
        approved_by=approved_by,
        approved_at=approved_at,
        memo=memo,
    )


# ---------------------------------------------------------------------------
# 승인 / 반려 / 철회 service (TASK 11)
# ---------------------------------------------------------------------------
# 승인 큐 대상(= PENDING 가능) 거래 유형
_PENDING_QUEUE_TYPES = (TransactionType.INITIAL_COUNT, TransactionType.ADJUSTMENT)


@transaction.atomic
def approve_transaction(*, user, transaction_obj, review_note=""):
    """PENDING 거래 승인. (TECH_SPEC §11 / PRODUCT_SPEC §5.8, §10.12)

    - 권한: MANAGER 이상
    - row lock + 상태 재확인 (PENDING 만 승인 가능)
    - INITIAL_COUNT: 승인 시점 APPROVED 중복 재검사
    - ADJUSTMENT: 승인 후 현재고 음수 방지
    - approved_by / approved_at 기록
    """
    if not is_manager_or_above(user):
        raise PermissionDeniedError("승인 권한이 없습니다. (MANAGER 이상)")

    tx = _lock_transaction(transaction_obj)
    if tx.status != TransactionStatus.PENDING:
        raise InvalidTransactionStateError(
            "PENDING 상태의 거래만 승인할 수 있습니다."
        )
    if tx.transaction_type not in _PENDING_QUEUE_TYPES:
        raise InvalidTransactionStateError(
            "승인 대상은 INITIAL_COUNT / ADJUSTMENT 거래뿐입니다."
        )

    locked_mi = _lock_managed_item(tx.managed_item)

    if tx.transaction_type == TransactionType.INITIAL_COUNT:
        # 승인 시점 유일성 재검사 (TECH_SPEC §5.6 승인 시점 규칙)
        if has_approved_initial_count(locked_mi):
            raise DuplicateInitialCountError(
                "이미 승인된 초기재고가 있어 승인할 수 없습니다."
            )
    else:  # ADJUSTMENT
        current = get_current_stock(locked_mi)
        if current + tx.quantity_delta < 0:
            raise InsufficientStockError(
                "승인 시 현재고가 음수가 되어 승인할 수 없습니다."
            )

    tx.status = TransactionStatus.APPROVED
    tx.approved_by = user
    tx.approved_at = timezone.now()
    if review_note:
        tx.review_note = review_note
    tx.save(
        update_fields=[
            "status",
            "approved_by",
            "approved_at",
            "review_note",
            "updated_at",
        ]
    )
    return tx


@transaction.atomic
def reject_transaction(*, user, transaction_obj, review_note):
    """PENDING 거래 반려. (TECH_SPEC §11)

    - 권한: MANAGER 이상
    - review_note 필수
    - 반려 시에도 approved_by / approved_at 를 기록한다. (PRODUCT_SPEC §10.12)
    """
    if not is_manager_or_above(user):
        raise PermissionDeniedError("반려 권한이 없습니다. (MANAGER 이상)")
    if not review_note or not str(review_note).strip():
        raise InventoryError("반려 사유(review_note)는 필수입니다.")

    tx = _lock_transaction(transaction_obj)
    if tx.status != TransactionStatus.PENDING:
        raise InvalidTransactionStateError(
            "PENDING 상태의 거래만 반려할 수 있습니다."
        )

    tx.status = TransactionStatus.REJECTED
    tx.approved_by = user
    tx.approved_at = timezone.now()
    tx.review_note = review_note
    tx.save(
        update_fields=[
            "status",
            "approved_by",
            "approved_at",
            "review_note",
            "updated_at",
        ]
    )
    return tx


@transaction.atomic
def withdraw_pending_transaction(*, user, transaction_obj, cancel_reason):
    """PENDING 거래 철회. (TECH_SPEC §11 / PRODUCT_SPEC §6.2)

    - 권한: 거래 생성자 또는 MANAGER 이상
    - cancel_reason 필수
    - PENDING → CANCELED, canceled_by / canceled_at 기록
    """
    tx = _lock_transaction(transaction_obj)

    if not (tx.created_by_id == getattr(user, "id", None) or is_manager_or_above(user)):
        raise PermissionDeniedError("철회 권한이 없습니다. (생성자 또는 MANAGER 이상)")
    if not cancel_reason or not str(cancel_reason).strip():
        raise InventoryError("철회 사유(cancel_reason)는 필수입니다.")
    if tx.status != TransactionStatus.PENDING:
        raise InvalidTransactionStateError(
            "PENDING 상태의 거래만 철회할 수 있습니다."
        )

    tx.status = TransactionStatus.CANCELED
    tx.canceled_by = user
    tx.canceled_at = timezone.now()
    tx.cancel_reason = cancel_reason
    tx.save(
        update_fields=[
            "status",
            "canceled_by",
            "canceled_at",
            "cancel_reason",
            "updated_at",
        ]
    )
    return tx
