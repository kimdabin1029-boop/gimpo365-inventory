"""inventory URL. (TECH_SPEC §13)

조회 화면(TASK 15)까지 추가. 생성/상태변경 URL 은 TASK 16~17 에서 추가한다.
"""

from django.urls import path

from inventory.views import (
    InventoryDashboardView,
    LowStockListView,
    StockListView,
    TransactionListView,
)

app_name = "inventory"

urlpatterns = [
    path("dashboard/", InventoryDashboardView.as_view(), name="dashboard"),
    path("stock/", StockListView.as_view(), name="stock_list"),
    path("low-stock/", LowStockListView.as_view(), name="low_stock"),
    path("transactions/", TransactionListView.as_view(), name="transaction_list"),
]
