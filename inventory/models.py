from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CheckConstraint, Index, Q, UniqueConstraint
from django.utils import timezone


# ---------------------------------------------------------------------------
# 고정 선택값 (TECH_SPEC §7) — Django TextChoices
# ---------------------------------------------------------------------------
class ItemCategory(models.TextChoices):
    BEAUTY_SUPPLY = "BEAUTY_SUPPLY", "미용소모품"
    MEDICAL_SUPPLY = "MEDICAL_SUPPLY", "의료용품"
    HYGIENE_SUPPLY = "HYGIENE_SUPPLY", "위생용품"
    MEDICINE = "MEDICINE", "의약품"
    GENERAL_SUPPLY = "GENERAL_SUPPLY", "일반소모품"
    DEDICATED_SUPPLY = "DEDICATED_SUPPLY", "전용소모품"
    OTHER = "OTHER", "기타"


class Unit(models.TextChoices):
    EA = "EA", "EA"
    BOX = "BOX", "BOX"
    PACK = "PACK", "PACK"
    P = "P", "P"
    ROLL = "ROLL", "ROLL"
    BOTTLE = "BOTTLE", "BOTTLE"
    VIAL = "VIAL", "VIAL"
    AMP = "AMP", "AMP"
    ML = "ML", "ML"
    G = "G", "G"
    KG = "KG", "KG"
    SET = "SET", "SET"
    OTHER = "OTHER", "OTHER"


class TransactionType(models.TextChoices):
    INITIAL_COUNT = "INITIAL_COUNT", "최초 재고 입력"
    IN = "IN", "입고"
    OUT_USE = "OUT_USE", "사용"
    OUT_DISCARD = "OUT_DISCARD", "폐기"
    OUT_LOST = "OUT_LOST", "분실"
    OUT_GIFT = "OUT_GIFT", "증정"
    OUT_OTHER = "OUT_OTHER", "기타출고"
    ADJUSTMENT = "ADJUSTMENT", "실사조정"


class TransactionStatus(models.TextChoices):
    PENDING = "PENDING", "대기"
    APPROVED = "APPROVED", "승인"
    REJECTED = "REJECTED", "반려"
    CANCELED = "CANCELED", "취소"


# 출고 계열 (quantity_delta 음수)
OUT_TRANSACTION_TYPES = frozenset(
    {
        TransactionType.OUT_USE,
        TransactionType.OUT_DISCARD,
        TransactionType.OUT_LOST,
        TransactionType.OUT_GIFT,
        TransactionType.OUT_OTHER,
    }
)


# ---------------------------------------------------------------------------
# Supplier (TECH_SPEC §6.2)
# ---------------------------------------------------------------------------
class Supplier(models.Model):
    name = models.CharField(max_length=150, unique=True)
    phone = models.CharField(max_length=50, blank=True, default="")
    homepage = models.URLField(max_length=255, blank=True, default="")
    manager_name = models.CharField(max_length=100, blank=True, default="")
    manager_phone = models.CharField(max_length=50, blank=True, default="")
    memo = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "공급업체"
        verbose_name_plural = "공급업체"

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Item (TECH_SPEC §6.3)
# ---------------------------------------------------------------------------
class Item(models.Model):
    """전역 품목 마스터.

    name 단독 unique. specification 은 설명용이며 unique 기준이 아니다.
    구분 정보는 name 에 포함한다. (예: 거즈 5x5, 거즈 10x10, 니들 30G)
    """

    name = models.CharField(max_length=150, unique=True)
    # category 는 default 없음 (TECH_SPEC §6.3)
    category = models.CharField(max_length=30, choices=ItemCategory.choices)
    specification = models.CharField(max_length=150, blank=True, default="")
    memo = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "품목"
        verbose_name_plural = "품목"

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# ManagedItem (TECH_SPEC §6.4) — Department + Item
# ---------------------------------------------------------------------------
class ManagedItem(models.Model):
    item = models.ForeignKey(
        "inventory.Item",
        on_delete=models.PROTECT,
        related_name="managed_items",
    )
    department = models.ForeignKey(
        "core.Department",
        on_delete=models.PROTECT,
        related_name="managed_items",
    )
    unit = models.CharField(max_length=20, choices=Unit.choices, default=Unit.EA)
    minimum_stock = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    storage_location = models.CharField(max_length=150, blank=True, default="")
    default_supplier = models.ForeignKey(
        "inventory.Supplier",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="managed_items",
    )
    is_active = models.BooleanField(default=True)
    memo = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["department", "item"]
        verbose_name = "관리품목"
        verbose_name_plural = "관리품목"
        constraints = [
            models.UniqueConstraint(
                fields=["department", "item"],
                name="uniq_managed_item_department_item",
            ),
        ]

    def clean(self):
        """운영 개시 후 unit 변경 금지. (TECH_SPEC §6.4)

        해당 ManagedItem 에 APPROVED StockTransaction 이 1건 이상 있으면
        unit 변경을 차단한다.
        """
        super().clean()
        if not self.pk:
            return
        old_unit = (
            ManagedItem.objects.filter(pk=self.pk)
            .values_list("unit", flat=True)
            .first()
        )
        if old_unit is not None and old_unit != self.unit:
            has_approved = StockTransaction.objects.filter(
                managed_item=self,
                status=TransactionStatus.APPROVED,
            ).exists()
            if has_approved:
                raise ValidationError(
                    {
                        "unit": "운영 개시 후에는 단위를 변경할 수 없습니다. "
                        "(APPROVED 거래 존재 / TECH_SPEC §6.4)"
                    }
                )

    def __str__(self):
        return f"{self.department} / {self.item} ({self.unit})"


# ---------------------------------------------------------------------------
# StockTransaction (TECH_SPEC §6.5) — 재고 거래 원장
# ---------------------------------------------------------------------------
class StockTransaction(models.Model):
    """모든 재고 변동을 기록하는 단일 원장.

    현재고 = APPROVED StockTransaction.quantity_delta 합계 (TECH_SPEC §6.5)

    주의: 생성/상태변경은 반드시 inventory/services.py 를 통해서만 수행한다.
    (View/Form/Admin 직접 create/save 금지 — TECH_SPEC §0)
    테스트 fixture/factory 에서는 제약조건 검증 목적상 직접 생성 가능.
    """

    managed_item = models.ForeignKey(
        "inventory.ManagedItem",
        on_delete=models.PROTECT,
        related_name="stock_transactions",
    )
    transaction_type = models.CharField(
        max_length=30, choices=TransactionType.choices
    )
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.PENDING,
    )
    quantity_input = models.DecimalField(
        max_digits=12, decimal_places=3, default=0
    )
    quantity_delta = models.DecimalField(
        max_digits=12, decimal_places=3, default=0
    )
    expected_quantity = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True
    )
    actual_quantity = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True
    )
    occurred_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_stock_transactions",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_stock_transactions",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    supplier = models.ForeignKey(
        "inventory.Supplier",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="stock_transactions",
    )
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    expiration_date = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True, default="")
    review_note = models.TextField(blank=True, default="")
    memo = models.TextField(blank=True, default="")
    canceled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="canceled_stock_transactions",
    )
    canceled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.TextField(blank=True, default="")
    # 주문서 기반 입고 연결 (v0.2.1). 주문 없이 등록한 일반 입고는 null.
    # OrderItem 삭제 시 연결 거래가 함께 삭제되면 안 되므로 PROTECT.
    source_order_item = models.ForeignKey(
        "inventory.OrderItem",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="stock_transactions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "재고 거래"
        verbose_name_plural = "재고 거래"
        # 거래 이력 정렬 (TECH_SPEC §13.3 / PRODUCT_SPEC §10.14)
        ordering = ["-occurred_at", "-created_at", "-id"]
        constraints = [
            # ManagedItem 당 APPROVED INITIAL_COUNT 최대 1건 (TECH_SPEC §8)
            UniqueConstraint(
                fields=["managed_item"],
                condition=Q(
                    transaction_type=TransactionType.INITIAL_COUNT,
                    status=TransactionStatus.APPROVED,
                ),
                name="uniq_approved_initial_count_per_managed_item",
            ),
            # quantity_input >= 0
            CheckConstraint(
                condition=Q(quantity_input__gte=0),
                name="ck_stock_tx_quantity_input_gte_0",
            ),
            # expected_quantity >= 0 또는 null
            CheckConstraint(
                condition=Q(expected_quantity__gte=0)
                | Q(expected_quantity__isnull=True),
                name="ck_stock_tx_expected_quantity_gte_0_or_null",
            ),
            # actual_quantity >= 0 또는 null
            CheckConstraint(
                condition=Q(actual_quantity__gte=0)
                | Q(actual_quantity__isnull=True),
                name="ck_stock_tx_actual_quantity_gte_0_or_null",
            ),
            # unit_price >= 0 또는 null
            CheckConstraint(
                condition=Q(unit_price__gte=0) | Q(unit_price__isnull=True),
                name="ck_stock_tx_unit_price_gte_0_or_null",
            ),
            # quantity_delta 는 음수 가능 — 제약 없음 (TECH_SPEC §8)
        ]
        indexes = [
            Index(
                fields=["managed_item", "status"],
                name="idx_stock_tx_mi_status",
            ),
        ]

    def __str__(self):
        return f"[{self.status}] {self.transaction_type} {self.quantity_delta} ({self.managed_item})"


# ---------------------------------------------------------------------------
# 주문 (v0.2.0) — 주문 장바구니 / 주문 / 주문품목
# ---------------------------------------------------------------------------
# 주의: 주문(Order)은 현재고를 변경하지 않는다. 실제 재고 증가는 입고(StockTransaction IN)
#       으로만 발생한다. Order 와 StockTransaction 은 별개 도메인이다. (합치지 않음)
class OrderStatus(models.TextChoices):
    ORDERED = "ORDERED", "주문완료"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED", "부분입고"
    RECEIVED = "RECEIVED", "입고완료"
    CANCELED = "CANCELED", "취소"


class OrderCart(models.Model):
    """사용자별 주문 장바구니. 주문 확정 전 임시 보관 공간. (v0.2.0)"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="order_cart",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "주문 장바구니"
        verbose_name_plural = "주문 장바구니"

    def __str__(self):
        return f"Cart({self.user})"


class CartItem(models.Model):
    """주문 장바구니 항목. (managed_item + supplier) 조합 단위. (v0.2.0)"""

    cart = models.ForeignKey(
        "inventory.OrderCart", on_delete=models.CASCADE, related_name="items"
    )
    managed_item = models.ForeignKey(
        "inventory.ManagedItem", on_delete=models.PROTECT, related_name="cart_items"
    )
    supplier = models.ForeignKey(
        "inventory.Supplier",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cart_items",
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    memo = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "장바구니 항목"
        verbose_name_plural = "장바구니 항목"
        constraints = [
            # 같은 장바구니 안에서 (관리품목 + 공급업체) 조합은 1행만.
            # (supplier 가 NULL 인 경우의 중복 방지는 service 계층에서 함께 처리한다.)
            UniqueConstraint(
                fields=["cart", "managed_item", "supplier"],
                name="uniq_cart_item_mi_supplier",
            ),
        ]

    def __str__(self):
        return f"CartItem({self.managed_item}, {self.quantity})"


class Order(models.Model):
    """주문 1건. 하나의 공급업체에 대한 주문. 현재고에는 영향을 주지 않는다. (v0.2.0)"""

    internal_order_no = models.CharField(
        max_length=20, unique=True, editable=False
    )
    external_order_no = models.CharField(max_length=100, blank=True, default="")
    supplier = models.ForeignKey(
        "inventory.Supplier", on_delete=models.PROTECT, related_name="orders"
    )
    ordered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    order_date = models.DateField(default=timezone.localdate)
    ordered_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20, choices=OrderStatus.choices, default=OrderStatus.ORDERED
    )
    memo = models.TextField(blank=True, default="")
    canceled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="canceled_orders",
    )
    canceled_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="received_orders",
    )
    received_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-ordered_at", "-id"]
        verbose_name = "주문"
        verbose_name_plural = "주문"

    def __str__(self):
        return f"{self.internal_order_no} [{self.status}] {self.supplier}"


class OrderItem(models.Model):
    """주문 품목. 주문 안의 개별 관리품목. (v0.2.0)"""

    order = models.ForeignKey(
        "inventory.Order", on_delete=models.CASCADE, related_name="items"
    )
    managed_item = models.ForeignKey(
        "inventory.ManagedItem", on_delete=models.PROTECT, related_name="order_items"
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    memo = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "주문 품목"
        verbose_name_plural = "주문 품목"

    def __str__(self):
        return f"OrderItem({self.managed_item}, {self.quantity})"
