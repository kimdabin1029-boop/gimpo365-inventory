from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import ListView, TemplateView

from accounts.models import Role
from accounts.permissions import has_role_at_least, is_manager_or_above
from inventory.exceptions import InventoryError
from inventory.models import StockTransaction, TransactionType
from inventory.forms import (
    AdjustmentRequestForm,
    ApproveTransactionForm,
    BulkApproveInitialCountsForm,
    CancelTransactionForm,
    PendingTransactionFilterForm,
    RejectTransactionForm,
    StockFilterForm,
    StockInForm,
    StockOutForm,
    TransactionFilterForm,
    WithdrawPendingTransactionForm,
)
from inventory.permissions import can_cancel_transaction
from inventory.selectors import (
    get_low_stock_managed_items,
    get_managed_items_with_current_stock,
    get_pending_transactions,
    get_transactions,
    has_approved_initial_count,
)
from inventory.services import (
    approve_transaction,
    bulk_approve_initial_counts,
    cancel_transaction,
    create_stock_in,
    create_stock_out,
    reject_transaction,
    request_adjustment,
    request_initial_count,
    withdraw_pending_transaction,
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

        # 최소재고 이하 품목: 권한 범위 내, 대시보드에는 최대 8건만 노출(나머지는 전체보기).
        low_stock_qs = get_low_stock_managed_items(user)
        ctx["low_stock_count"] = low_stock_qs.count()
        DASHBOARD_LOW_STOCK_LIMIT = 8
        low_stock_items = list(low_stock_qs[:DASHBOARD_LOW_STOCK_LIMIT])
        for item in low_stock_items:
            # 상태: 현재고 0 이하면 "재고없음", 그 외(최소재고 이하)는 "최소재고 이하"
            item.is_out = item.current_stock <= 0
        ctx["low_stock_items"] = low_stock_items
        ctx["low_stock_more"] = ctx["low_stock_count"] - len(low_stock_items)

        ctx["my_today_count"] = (
            get_transactions(user)
            .filter(created_by=user, created_at__date=today)
            .count()
        )

        ctx["is_manager"] = is_manager_or_above(user)
        # 실사조정 요청(최초 재고 입력 포함)은 TEAM_LEADER 이상만 (v0.1.1)
        ctx["can_request_adjustment"] = has_role_at_least(user, Role.TEAM_LEADER)
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

    def _resolve_date_range(self):
        """거래일자(occurred_at) 기간. 기본 오늘~오늘.

        빠른필터 range= today / 7d / month / 3m (최근 3개월).
        '전체'는 데이터 과다 우려로 제거(B-6). 더 긴 기간은 수동 시작/종료일로 조회.
        """
        today = timezone.localdate()
        rng = self.request.GET.get("range")
        if rng == "7d":
            return today - timedelta(days=6), today
        if rng == "month":
            return today.replace(day=1), today
        if rng == "3m":
            return today - timedelta(days=90), today
        if rng == "today":
            return today, today
        gf = parse_date(self.request.GET.get("date_from") or "")
        gt = parse_date(self.request.GET.get("date_to") or "")
        if gf or gt:
            return gf, gt
        return today, today  # 기본값

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
        qs = get_transactions(self.request.user, filters)
        self._range_from, self._range_to = self._resolve_date_range()
        if self._range_from:
            qs = qs.filter(occurred_at__date__gte=self._range_from)
        if self._range_to:
            qs = qs.filter(occurred_at__date__lte=self._range_to)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        for tx in ctx["object_list"]:
            tx.can_cancel = can_cancel_transaction(user, tx)
        ctx["filter_form"] = self._form
        ctx["range_from"] = self._range_from
        ctx["range_to"] = self._range_to
        ctx["active_range"] = self.request.GET.get("range", "")
        return ctx


class TransactionDetailView(LoginRequiredMixin, View):
    """거래 상세. 메모 등 전체 정보를 확인한다. (v0.1.2 알파 피드백)

    조회 전용. 접근 범위는 거래이력(get_transactions)과 동일하게 제한한다.
    즉 STAFF / TEAM_LEADER 는 본인 부서 거래만, MANAGER / ADMIN 은 전체.
    권한 밖 거래는 get_object_or_404 로 404 처리되어 범위가 넓어지지 않는다.
    """

    template_name = "inventory/transaction_detail.html"

    def get(self, request, *args, **kwargs):
        # get_transactions(user) 가 권한 범위를 그대로 적용하므로 별도 권한검사 불필요.
        tx = get_object_or_404(get_transactions(request.user), pk=kwargs["pk"])
        return render(
            request,
            self.template_name,
            {
                "tx": tx,
                "can_cancel": can_cancel_transaction(request.user, tx),
            },
        )


class AdjustmentRequestListView(LoginRequiredMixin, ListView):
    """실사조정 내역 — 요청 처리 결과/사유 확인. (v0.1.1 / PRODUCT_SPEC §10.10)

    권한: STAFF 본인 요청만 / TEAM_LEADER 본인 부서 / MANAGER·ADMIN 권한 범위.
    조회 전용. 승인/반려/철회 로직은 변경하지 않는다.
    """

    template_name = "inventory/adjustment_list.html"
    context_object_name = "transactions"
    paginate_by = 50

    def get_queryset(self):
        user = self.request.user
        # 최초 재고 입력(INITIAL_COUNT) + 실사조정(ADJUSTMENT) 을 함께 보여준다.
        qs = get_transactions(user).filter(
            transaction_type__in=[
                TransactionType.INITIAL_COUNT,
                TransactionType.ADJUSTMENT,
            ]
        )
        # STAFF 는 본인이 요청한 것만 (현재 STAFF 는 생성 권한 없음)
        if not has_role_at_least(user, Role.TEAM_LEADER):
            qs = qs.filter(created_by=user)
        return qs


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

    # 출고 화면에서만 "출고 후 예상 재고" 표시
    show_projected = False
    # 실사조정 통합 화면에서만 모드 안내(최초 재고 입력/실사조정) 표시
    adjustment_mode = False

    def _render(self, form):
        return render(
            self.request,
            self.template_name,
            {
                "form": form,
                "page_title": self.page_title,
                "show_projected": self.show_projected,
                "adjustment_mode": self.adjustment_mode,
            },
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
    show_projected = True  # 출고 후 예상 재고 표시

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
    """실사조정 요청 (최초 재고 입력 / 실사조정 통합). TEAM_LEADER 이상.

    선택 품목에 승인된 최초 재고가 없으면 request_initial_count(INITIAL_COUNT),
    있으면 request_adjustment(ADJUSTMENT) 로 라우팅한다. (내부 거래유형 유지)
    """

    form_class = AdjustmentRequestForm
    page_title = "실사조정 요청"
    adjustment_mode = True  # 템플릿 모드 안내 활성

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not has_role_at_least(
            request.user, Role.TEAM_LEADER
        ):
            raise PermissionDenied("실사조정 요청 권한이 없습니다. (TEAM_LEADER 이상)")
        return super().dispatch(request, *args, **kwargs)

    def perform(self, user, cd):
        mi = cd["managed_item"]
        if has_approved_initial_count(mi):
            request_adjustment(
                user=user, managed_item=mi,
                actual_quantity=cd["actual_quantity"], reason=cd["reason"],
                occurred_at=cd.get("occurred_at"), memo=cd.get("memo", ""),
            )
            self.success_message = "실사조정 요청이 등록되었습니다. (승인 대기)"
        else:
            request_initial_count(
                user=user, managed_item=mi, quantity=cd["actual_quantity"],
                occurred_at=cd.get("occurred_at"), memo=cd.get("memo", ""),
            )
            self.success_message = "최초 재고 입력이 등록되었습니다."


# 별도 '초기재고 입력' 화면은 실사조정 요청(AdjustmentRequestView)으로 통합되었다. (v0.1.1)
# 기존 URL(initial_count_new)은 urls.py 에서 실사조정 요청으로 redirect 한다.


# ---------------------------------------------------------------------------
# 상태 변경 화면 (TASK 17)
# ---------------------------------------------------------------------------
class ManagerRequiredMixin(LoginRequiredMixin):
    """MANAGER 이상만 접근 허용. 비로그인은 로그인으로 redirect, 그 외엔 403."""

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if user.is_authenticated and not is_manager_or_above(user):
            raise PermissionDenied("MANAGER 이상만 접근할 수 있습니다.")
        return super().dispatch(request, *args, **kwargs)


class PendingTransactionListView(ManagerRequiredMixin, ListView):
    """승인 큐: PENDING INITIAL_COUNT / ADJUSTMENT. (PRODUCT_SPEC §10.12)"""

    template_name = "inventory/pending_list.html"
    context_object_name = "transactions"
    paginate_by = 50

    def get_queryset(self):
        self._form = PendingTransactionFilterForm(
            self.request.GET or None, user=self.request.user
        )
        filters = {}
        if self._form.is_valid():
            cd = self._form.cleaned_data
            if cd.get("department"):
                filters["department"] = cd["department"]
            if cd.get("transaction_type"):
                filters["transaction_type"] = cd["transaction_type"]
        return get_pending_transactions(self.request.user, filters)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter_form"] = self._form
        ctx["bulk_form"] = BulkApproveInitialCountsForm(user=self.request.user)
        return ctx


class _TransactionActionView(LoginRequiredMixin, View):
    """단일 거래 상태 변경 공통 View.

    - GET: 확인 Form 렌더링만 (상태 변경 없음)
    - POST: form 검증 후 service 함수 호출 (상태 변경)
    - GET/POST 양쪽에서 check_permission 으로 권한 재검사
    - 상태 변경은 service 함수만 수행 (tx.status 직접 변경 / 직접 create 금지)
    """

    form_class = None
    template_name = "inventory/confirm_action.html"
    page_title = ""
    success_message = ""
    redirect_url_name = "inventory:pending_list"

    def get_object(self):
        return get_object_or_404(StockTransaction, pk=self.kwargs["pk"])

    def check_permission(self, user, tx):
        raise NotImplementedError

    def _render(self, tx, form):
        return render(
            self.request,
            self.template_name,
            {
                "tx": tx,
                "form": form,
                "page_title": self.page_title,
                "action_url": self.request.path,
            },
        )

    def get(self, request, *args, **kwargs):
        tx = self.get_object()
        self.check_permission(request.user, tx)  # GET 권한 재검사
        return self._render(tx, self.form_class())

    def post(self, request, *args, **kwargs):
        tx = self.get_object()
        self.check_permission(request.user, tx)  # POST 권한 재검사
        form = self.form_class(request.POST)
        if not form.is_valid():
            return self._render(tx, form)
        try:
            self.perform(request.user, tx, form.cleaned_data)
        except InventoryError as exc:
            messages.error(request, str(exc))
            return self._render(tx, form)
        messages.success(request, self.success_message)
        return redirect(reverse(self.redirect_url_name))

    def perform(self, user, tx, cd):
        raise NotImplementedError


class ApproveTransactionView(_TransactionActionView):
    form_class = ApproveTransactionForm
    page_title = "거래 승인"
    success_message = "거래를 승인했습니다."

    def check_permission(self, user, tx):
        if not is_manager_or_above(user):
            raise PermissionDenied("승인 권한이 없습니다.")

    def perform(self, user, tx, cd):
        approve_transaction(
            user=user, transaction_obj=tx, review_note=cd.get("review_note", "")
        )


class RejectTransactionView(_TransactionActionView):
    form_class = RejectTransactionForm
    page_title = "거래 반려"
    success_message = "거래를 반려했습니다."

    def check_permission(self, user, tx):
        if not is_manager_or_above(user):
            raise PermissionDenied("반려 권한이 없습니다.")

    def perform(self, user, tx, cd):
        reject_transaction(
            user=user, transaction_obj=tx, review_note=cd["review_note"]
        )


class WithdrawPendingTransactionView(_TransactionActionView):
    form_class = WithdrawPendingTransactionForm
    page_title = "PENDING 거래 철회"
    success_message = "거래를 철회했습니다."

    def check_permission(self, user, tx):
        if not (tx.created_by_id == user.id or is_manager_or_above(user)):
            raise PermissionDenied("철회 권한이 없습니다.")

    def perform(self, user, tx, cd):
        withdraw_pending_transaction(
            user=user, transaction_obj=tx, cancel_reason=cd["cancel_reason"]
        )


class CancelTransactionView(_TransactionActionView):
    form_class = CancelTransactionForm
    page_title = "거래 취소"
    success_message = "거래를 취소했습니다."
    redirect_url_name = "inventory:transaction_list"

    def check_permission(self, user, tx):
        # 권한 + 상태/유형 조건을 모두 포함 (can_cancel_transaction)
        if not can_cancel_transaction(user, tx):
            raise PermissionDenied("해당 거래를 취소할 권한이 없습니다.")

    def perform(self, user, tx, cd):
        cancel_transaction(
            user=user, transaction_obj=tx, cancel_reason=cd["cancel_reason"]
        )


class BulkApproveInitialCountsView(ManagerRequiredMixin, View):
    """초기재고 일괄 승인. POST 전용. (PRODUCT_SPEC §10.13)"""

    def get(self, request, *args, **kwargs):
        # GET 으로는 상태 변경하지 않는다 → 승인 큐로 돌려보낸다.
        return redirect(reverse("inventory:pending_list"))

    def post(self, request, *args, **kwargs):
        form = BulkApproveInitialCountsForm(request.POST, user=request.user)
        if not form.is_valid():
            messages.error(request, "선택된 초기재고가 없습니다.")
            return redirect(reverse("inventory:pending_list"))
        ids = [tx.pk for tx in form.cleaned_data["selected"]]
        result = bulk_approve_initial_counts(user=request.user, transaction_ids=ids)
        messages.success(
            request,
            f"승인 완료: {len(result['approved'])}건, "
            f"승인 제외: {len(result['skipped'])}건",
        )
        return redirect(reverse("inventory:pending_list"))
