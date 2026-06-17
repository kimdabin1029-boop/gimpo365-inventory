from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, TemplateView

from accounts.permissions import is_manager_or_above
from inventory.exceptions import InventoryError
from inventory.forms import (
    AdjustmentRequestForm,
    InitialCountForm,
    StockFilterForm,
    StockInForm,
    StockOutForm,
    TransactionFilterForm,
)
from inventory.permissions import can_cancel_transaction
from inventory.selectors import (
    get_low_stock_managed_items,
    get_managed_items_with_current_stock,
    get_pending_transactions,
    get_transactions,
)
from inventory.services import (
    create_stock_in,
    create_stock_out,
    request_adjustment,
    request_initial_count,
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


# ---------------------------------------------------------------------------
# 생성 화면 (TASK 16)
# ---------------------------------------------------------------------------
class _ServiceCreateView(LoginRequiredMixin, View):
    """user-aware Form → service 함수 호출 패턴.

    - GET: 빈 Form 렌더
    - POST: form 검증 후 cleaned_data 를 service 에 전달
      - 성공: 성공 메시지 + 같은 Form 화면 유지(빈 새 Form 렌더, 연속 입력)
      - 실패(InventoryError): 오류 메시지 + 입력값 유지 Form 재렌더
    - 원장 생성/상태변경은 service 함수만 수행한다. (ModelForm.save() / 직접 create 금지)
    """

    form_class = None
    template_name = "inventory/transaction_form.html"
    page_title = ""
    success_message = "저장되었습니다."

    def get_form(self, data=None):
        return self.form_class(user=self.request.user, data=data)

    def _render(self, form):
        return render(
            self.request,
            self.template_name,
            {"form": form, "page_title": self.page_title},
        )

    def get(self, request, *args, **kwargs):
        return self._render(self.get_form())

    def post(self, request, *args, **kwargs):
        form = self.get_form(data=request.POST)
        if not form.is_valid():
            return self._render(form)
        try:
            self.perform(request.user, form.cleaned_data)
        except InventoryError as exc:
            messages.error(request, str(exc))
            return self._render(form)
        messages.success(request, self.success_message)
        # 성공 후 같은 Form 화면 유지 (빈 새 Form)
        return self._render(self.get_form())

    def perform(self, user, cleaned_data):
        raise NotImplementedError


class StockInCreateView(_ServiceCreateView):
    form_class = StockInForm
    page_title = "입고 등록"
    success_message = "입고가 등록되었습니다."

    def perform(self, user, cd):
        create_stock_in(
            user=user,
            managed_item=cd["managed_item"],
            quantity=cd["quantity"],
            occurred_at=cd.get("occurred_at"),
            supplier=cd.get("supplier"),
            unit_price=cd.get("unit_price"),
            expiration_date=cd.get("expiration_date"),
            memo=cd.get("memo", ""),
        )


class StockOutCreateView(_ServiceCreateView):
    form_class = StockOutForm
    page_title = "출고 등록"
    success_message = "출고가 등록되었습니다."

    def perform(self, user, cd):
        create_stock_out(
            user=user,
            managed_item=cd["managed_item"],
            transaction_type=cd["transaction_type"],
            quantity=cd["quantity"],
            occurred_at=cd.get("occurred_at"),
            memo=cd.get("memo", ""),
        )


class AdjustmentRequestView(_ServiceCreateView):
    form_class = AdjustmentRequestForm
    page_title = "실사조정 요청"
    success_message = "실사조정 요청이 등록되었습니다. (승인 대기)"

    def perform(self, user, cd):
        request_adjustment(
            user=user,
            managed_item=cd["managed_item"],
            actual_quantity=cd["actual_quantity"],
            reason=cd["reason"],
            occurred_at=cd.get("occurred_at"),
            memo=cd.get("memo", ""),
        )


class InitialCountRequestView(_ServiceCreateView):
    form_class = InitialCountForm
    page_title = "초기재고 입력"
    success_message = "초기재고가 등록되었습니다."

    def perform(self, user, cd):
        request_initial_count(
            user=user,
            managed_item=cd["managed_item"],
            quantity=cd["quantity"],
            occurred_at=cd.get("occurred_at"),
            memo=cd.get("memo", ""),
        )
