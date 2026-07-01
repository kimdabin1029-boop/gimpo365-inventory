"""inventory URL. (TECH_SPEC §13)

조회 화면(TASK 15)까지 추가. 생성/상태변경 URL 은 TASK 16~17 에서 추가한다.
"""

from django.urls import path
from django.views.generic import RedirectView

from inventory.views import (
    AddToCartView,
    AdjustmentRequestListView,
    AdjustmentRequestView,
    ApproveTransactionView,
    BulkApproveInitialCountsView,
    CancelTransactionView,
    CartItemRemoveView,
    CartItemUpdateView,
    CartView,
    InboundPendingListView,
    InventoryDashboardView,
    LowStockListView,
    OrderCancelView,
    OrderConfirmView,
    OrderDetailView,
    OrderItemStockInView,
    OrderListView,
    PendingTransactionListView,
    RejectTransactionView,
    StockInCreateView,
    StockListView,
    StockOutCreateView,
    TransactionDetailView,
    TransactionListView,
    WithdrawPendingTransactionView,
)

app_name = "inventory"

urlpatterns = [
    path("dashboard/", InventoryDashboardView.as_view(), name="dashboard"),
    path("stock/", StockListView.as_view(), name="stock_list"),
    path("low-stock/", LowStockListView.as_view(), name="low_stock"),
    path("transactions/", TransactionListView.as_view(), name="transaction_list"),
    path(
        "transactions/<int:pk>/",
        TransactionDetailView.as_view(),
        name="transaction_detail",
    ),
    path("adjustments/", AdjustmentRequestListView.as_view(), name="adjustment_list"),
    # 생성 화면 (TASK 16)
    path("in/new/", StockInCreateView.as_view(), name="stock_in_new"),
    path("out/new/", StockOutCreateView.as_view(), name="stock_out_new"),
    path("adjustment/new/", AdjustmentRequestView.as_view(), name="adjustment_new"),
    # 초기재고 입력은 실사조정 요청으로 통합 → 기존 URL 은 redirect (v0.1.1)
    path(
        "initial-count/new/",
        RedirectView.as_view(pattern_name="inventory:adjustment_new", permanent=False),
        name="initial_count_new",
    ),
    # 상태 변경 화면 (TASK 17)
    path("pending/", PendingTransactionListView.as_view(), name="pending_list"),
    path("pending/<int:pk>/approve/", ApproveTransactionView.as_view(), name="approve"),
    path("pending/<int:pk>/reject/", RejectTransactionView.as_view(), name="reject"),
    path(
        "pending/<int:pk>/withdraw/",
        WithdrawPendingTransactionView.as_view(),
        name="withdraw",
    ),
    path(
        "transactions/<int:pk>/cancel/",
        CancelTransactionView.as_view(),
        name="cancel",
    ),
    path(
        "initial-counts/bulk-approve/",
        BulkApproveInitialCountsView.as_view(),
        name="bulk_approve",
    ),
    # 주문 장바구니 / 주문 (v0.2.0)
    path("cart/", CartView.as_view(), name="cart"),
    path("cart/add/", AddToCartView.as_view(), name="cart_add"),
    path("cart/items/<int:pk>/update/", CartItemUpdateView.as_view(), name="cart_item_update"),
    path("cart/items/<int:pk>/remove/", CartItemRemoveView.as_view(), name="cart_item_remove"),
    path("cart/confirm/", OrderConfirmView.as_view(), name="order_confirm"),
    path("orders/", OrderListView.as_view(), name="order_list"),
    path("orders/<int:pk>/", OrderDetailView.as_view(), name="order_detail"),
    path("orders/<int:pk>/cancel/", OrderCancelView.as_view(), name="order_cancel"),
    # 입고대기 품목 + 주문 품목 기반 입고등록 (v0.2.1)
    path("inbound-pending/", InboundPendingListView.as_view(), name="inbound_pending"),
    path(
        "order-items/<int:pk>/stock-in/",
        OrderItemStockInView.as_view(),
        name="order_item_stock_in",
    ),
]
