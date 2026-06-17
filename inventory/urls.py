"""inventory URL. (TECH_SPEC §13)

조회 화면(TASK 15)까지 추가. 생성/상태변경 URL 은 TASK 16~17 에서 추가한다.
"""

from django.urls import path

from inventory.views import (
    AdjustmentRequestView,
    InitialCountRequestView,
    InventoryDashboardView,
    LowStockListView,
    StockInCreateView,
    StockListView,
    StockOutCreateView,
    TransactionListView,
)

app_name = "inventory"

urlpatterns = [
    path("dashboard/", InventoryDashboardView.as_view(), name="dashboard"),
    path("stock/", StockListView.as_view(), name="stock_list"),
    path("low-stock/", LowStockListView.as_view(), name="low_stock"),
    path("transactions/", TransactionListView.as_view(), name="transaction_list"),
    # 생성 화면 (TASK 16)
    path("in/new/", StockInCreateView.as_view(), name="stock_in_new"),
    path("out/new/", StockOutCreateView.as_view(), name="stock_out_new"),
    path("adjustment/new/", AdjustmentRequestView.as_view(), name="adjustment_new"),
    path(
        "initial-count/new/",
        InitialCountRequestView.as_view(),
        name="initial_count_new",
    ),
]
