from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView

from accounts.permissions import is_manager_or_above
from inventory.selectors import (
    get_low_stock_managed_items,
    get_pending_transactions,
    get_transactions,
)


class InventoryDashboardView(LoginRequiredMixin, TemplateView):
    """재고 대시보드. (PRODUCT_SPEC §10.3~10.5)

    selector 만 사용하여 조회한다. 원장 변경 로직은 두지 않는다.
    """

    template_name = "inventory/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.localdate()

        ctx["low_stock_count"] = get_low_stock_managed_items(user).count()
        ctx["my_today_count"] = (
            get_transactions(user)
            .filter(created_by=user, created_at__date=today)
            .count()
        )

        ctx["is_manager"] = is_manager_or_above(user)
        if ctx["is_manager"]:
            ctx["pending_count"] = get_pending_transactions(user).count()
        return ctx
