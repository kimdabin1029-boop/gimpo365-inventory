from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import ListView, TemplateView

from accounts.permissions import is_manager_or_above
from inventory.forms import StockFilterForm, TransactionFilterForm
from inventory.permissions import can_cancel_transaction
from inventory.selectors import (
    get_low_stock_managed_items,
    get_managed_items_with_current_stock,
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


# ---------------------------------------------------------------------------
# 조회 화면 (TASK 15) — 모두 조회 전용. selector 만 사용한다.
# ---------------------------------------------------------------------------
class _StockFilterMixin:
    """StockFilterForm 의 cleaned_data 를 selector filters dict 로 변환."""

    def get_filter_form(self):
        return StockFilterForm(self.request.GET or None, user=self.request.user)

    def build_filters(self, form):
        filters = {}
        if form.is_valid():
            cd = form.cleaned_data
            if cd.get("department"):
                filters["department"] = cd["department"]
            if cd.get("category"):
                filters["category"] = cd["category"]
            if cd.get("storage_location"):
                filters["storage_location"] = cd["storage_location"]
            if cd.get("low_stock"):
                filters["low_stock"] = True
            if cd.get("is_active"):
                filters["is_active"] = True
        return filters


class StockListView(LoginRequiredMixin, _StockFilterMixin, ListView):
    """현재고 조회. (PRODUCT_SPEC §10.8)"""

    template_name = "inventory/stock_list.html"
    context_object_name = "items"
    paginate_by = 50

    def get_queryset(self):
        self._form = self.get_filter_form()
        return get_managed_items_with_current_stock(
            self.request.user, self.build_filters(self._form)
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter_form"] = self._form
        return ctx


class LowStockListView(LoginRequiredMixin, _StockFilterMixin, ListView):
    """최소재고 이하 품목. (PRODUCT_SPEC §10.9)"""

    template_name = "inventory/low_stock_list.html"
    context_object_name = "items"
    paginate_by = 50

    def get_queryset(self):
        self._form = self.get_filter_form()
        return get_low_stock_managed_items(
            self.request.user, self.build_filters(self._form)
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # 부족 수량 = 최소재고 - 현재고
        for item in ctx["object_list"]:
            item.shortage = item.minimum_stock - item.current_stock
        ctx["filter_form"] = self._form
        return ctx


class TransactionListView(LoginRequiredMixin, ListView):
    """거래 이력 조회. (PRODUCT_SPEC §10.14)

    각 거래에 can_cancel(취소 버튼 표시 여부)을 부여한다.
    버튼 숨김은 UX 일 뿐이며 실제 취소 권한은 TASK 17 cancel view 에서 재검사한다.
    """

    template_name = "inventory/transaction_list.html"
    context_object_name = "transactions"
    paginate_by = 50

    def get_filter_form(self):
        return TransactionFilterForm(self.request.GET or None, user=self.request.user)

    def get_queryset(self):
        self._form = self.get_filter_form()
        filters = {}
        if self._form.is_valid():
            cd = self._form.cleaned_data
            if cd.get("department"):
                filters["department"] = cd["department"]
            if cd.get("transaction_type"):
                filters["transaction_type"] = cd["transaction_type"]
            if cd.get("status"):
                filters["status"] = cd["status"]
        return get_transactions(self.request.user, filters)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        for tx in ctx["object_list"]:
            tx.can_cancel = can_cancel_transaction(user, tx)
        ctx["filter_form"] = self._form
        return ctx
