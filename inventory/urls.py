"""inventory URL. (TECH_SPEC §13)

TASK 14 단계에서는 dashboard 만 노출한다.
조회/생성/상태변경 URL 은 TASK 15~17 에서 추가한다.
"""

from django.urls import path

from inventory.views import InventoryDashboardView

app_name = "inventory"

urlpatterns = [
    path("dashboard/", InventoryDashboardView.as_view(), name="dashboard"),
]
