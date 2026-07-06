from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import ListView, TemplateView

from accounts.models import Role
from accounts.permissions import has_role_at_least, is_manager_or_above
from inventory.exceptions import InventoryError
from inventory.exports import (
    dated_filename,
    xlsx_multi_sheet_response,
    xlsx_response,
)
from inventory.master_data_checks import (
    item_rows,
    managed_item_rows,
    run_master_data_checks,
    supplier_rows,
)
from inventory.report_selectors import (
    get_export_transactions,
    get_monthly_summary,
    resolve_tx_date_range,
)
from inventory.models import StockTransaction, Supplier, TransactionType
from inventory.forms import (
    AddToCartForm,
    AdjustmentRequestForm,
    ApproveTransactionForm,
    BulkApproveInitialCountsForm,
    CancelTransactionForm,
    CartItemForm,
    ConfirmOrderForm,
    InboundPendingFilterForm,
    MonthlyReportForm,
    OrderFilterForm,
    OrderItemStockInForm,
    PendingTransactionFilterForm,
    RejectTransactionForm,
    RemainingCloseForm,
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
from inventory.detail_selectors import (
    get_managed_item_detail,
    get_managed_item_stats,
    get_recent_order_items_for_managed_item,
    get_recent_orders_for_supplier,
    get_recent_stock_ins_for_supplier,
    get_recent_transactions_for_managed_item,
    get_supplier_default_items,
    get_supplier_detail,
    get_supplier_stats,
    get_transaction_detail,
    get_transaction_order_link,
    get_unreceived_order_items_for_supplier,
)
from inventory.order_selectors import (
    get_order_item_for_user_or_none,
    get_order_items_with_progress,
    get_order_or_none,
    get_orders,
    get_pending_order_items,
    get_unreceived_orders,
    remaining_quantity,
)
from inventory.order_services import (
    add_to_cart,
    can_manage_order,
    cancel_order,
    close_remaining,
    confirm_order,
    create_stock_in_from_order_item,
    get_or_create_cart,
    remove_cart_item,
    update_cart_item,
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

        # 미입고 주문(ORDERED): 권한 범위 내 최대 5건 + 전체보기 링크 (v0.2.0)
        DASHBOARD_ORDER_LIMIT = 5
        unreceived = get_unreceived_orders(user)
        ctx["unreceived_count"] = unreceived.count()
        ctx["unreceived_orders"] = list(unreceived[:DASHBOARD_ORDER_LIMIT])
        ctx["unreceived_more"] = ctx["unreceived_count"] - len(ctx["unreceived_orders"])
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
    """재고현황 (전체 품목 / 최소재고 이하 통합). (PRODUCT_SPEC §10.8 / v0.2.1)

    빠른 필터: ?filter=low_stock 이면 최소재고 이하만 표시한다.
    """

    template_name = "inventory/stock_list.html"
    context_object_name = "items"
    paginate_by = 50

    def _low_only(self):
        # 통합 화면 빠른 필터. 과거 ?low_stock=on 링크도 계속 지원.
        return self.request.GET.get("filter") == "low_stock" or bool(
            self.request.GET.get("low_stock")
        )

    def get_queryset(self):
        self._form = self.get_filter_form()
        filters = self.build_filters(self._form)
        self._low = self._low_only()
        if self._low:
            filters["low_stock"] = True
        return get_managed_items_with_current_stock(self.request.user, filters)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # 부족 수량 = 최소재고 - 현재고 (최소재고 이하 표시용)
        for item in ctx["object_list"]:
            item.shortage = item.minimum_stock - item.current_stock
        ctx["filter_form"] = self._form
        ctx["suppliers"] = Supplier.objects.filter(is_active=True)  # 주문 담기용
        ctx["active_filter"] = "low_stock" if self._low else "all"
        return ctx


class LowStockListView(LoginRequiredMixin, View):
    """(v0.2.1) 최소재고 이하 품목 화면은 재고현황으로 통합됨 → 리다이렉트."""

    def get(self, request, *args, **kwargs):
        return redirect(reverse("inventory:stock_list") + "?filter=low_stock")


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
        # get_transaction_detail(user) 가 권한 범위를 그대로 적용하므로 별도 권한검사 불필요.
        tx = get_transaction_detail(request.user, kwargs["pk"])
        if tx is None:
            raise Http404("거래를 찾을 수 없습니다.")
        return render(
            request,
            self.template_name,
            {
                "tx": tx,
                "can_cancel": can_cancel_transaction(request.user, tx),
                # 주문 연결 정보(있으면). v0.2.1 source_order_item.
                "order_link": get_transaction_order_link(tx),
            },
        )


class ManagedItemDetailView(LoginRequiredMixin, View):
    """관리품목 상세 (읽기 전용). 권한 범위는 재고현황과 동일. (v0.2.2)

    현재고는 APPROVED 거래 합계(주석)로 표시한다. 범위 밖이면 404.
    """

    template_name = "inventory/managed_item_detail.html"

    def get(self, request, *args, **kwargs):
        mi = get_managed_item_detail(request.user, kwargs["pk"])
        if mi is None:
            raise Http404("관리품목을 찾을 수 없습니다.")
        return render(
            request,
            self.template_name,
            {
                "mi": mi,
                "stats": get_managed_item_stats(mi),
                "transactions": get_recent_transactions_for_managed_item(request.user, mi),
                "order_items": get_recent_order_items_for_managed_item(request.user, mi),
            },
        )


class SupplierDetailView(LoginRequiredMixin, View):
    """공급업체 상세 (읽기 전용). 비관리자는 권한 범위 관련 데이터만. (v0.2.2)"""

    template_name = "inventory/supplier_detail.html"

    def get(self, request, *args, **kwargs):
        supplier = get_supplier_detail(request.user, kwargs["pk"])
        if supplier is None:
            raise Http404("공급업체를 찾을 수 없습니다.")
        return render(
            request,
            self.template_name,
            {
                "supplier": supplier,
                "stats": get_supplier_stats(request.user, supplier),
                "default_items": get_supplier_default_items(request.user, supplier),
                "orders": get_recent_orders_for_supplier(request.user, supplier),
                "unreceived_items": get_unreceived_order_items_for_supplier(request.user, supplier),
                "stock_ins": get_recent_stock_ins_for_supplier(request.user, supplier),
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

    def get_form(self, data=None):
        # 주문 상세 "입고 등록으로 이동"에서 넘어온 managed_item/supplier 를 초기값으로 채운다.
        # (값 prefill 만; 실제 저장/현재고 변경은 기존 service 가 담당)
        if data is None:
            initial = {}
            mi = self.request.GET.get("managed_item")
            sup = self.request.GET.get("supplier")
            if mi:
                initial["managed_item"] = mi
            if sup:
                initial["supplier"] = sup
            if initial:
                return self.form_class(user=self.request.user, initial=initial)
        return self.form_class(user=self.request.user, data=data)

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


# ---------------------------------------------------------------------------
# 주문 장바구니 / 주문 (v0.2.0)
# ---------------------------------------------------------------------------
def _safe_next(request, default_name="inventory:stock_list"):
    """돌아갈 URL: POST next 파라미터(내부 경로만) 우선, 없으면 기본 화면."""
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and nxt.startswith("/"):
        return nxt
    return reverse(default_name)


class AddToCartView(LoginRequiredMixin, View):
    """관리품목을 주문 장바구니에 담는다. POST 전용. (v0.2.0)"""

    def post(self, request, *args, **kwargs):
        form = AddToCartForm(user=request.user, data=request.POST)
        if not form.is_valid():
            messages.error(request, "장바구니에 담지 못했습니다. 입력값을 확인해주세요.")
            return redirect(_safe_next(request))
        cd = form.cleaned_data
        try:
            add_to_cart(
                user=request.user,
                managed_item=cd["managed_item"],
                supplier=cd.get("supplier"),
                quantity=cd["quantity"],
                memo=cd.get("memo", ""),
            )
        except InventoryError as exc:
            messages.error(request, str(exc))
            return redirect(_safe_next(request))
        messages.success(
            request,
            f"주문 장바구니에 담았습니다: {cd['managed_item'].item.name}",
        )
        return redirect(_safe_next(request))


class CartView(LoginRequiredMixin, View):
    """주문 장바구니 화면. (v0.2.0)"""

    template_name = "inventory/cart.html"

    def get(self, request, *args, **kwargs):
        cart = get_or_create_cart(request.user)
        items = list(
            cart.items.select_related(
                "managed_item", "managed_item__item",
                "managed_item__department", "supplier",
            ).order_by("id")
        )
        return render(
            request,
            self.template_name,
            {
                "items": items,
                "suppliers": Supplier.objects.filter(is_active=True),
                "has_missing_supplier": any(i.supplier_id is None for i in items),
            },
        )


class CartItemUpdateView(LoginRequiredMixin, View):
    """장바구니 항목 수정 (수량/공급업체/메모). POST 전용. (v0.2.0)"""

    def post(self, request, *args, **kwargs):
        form = CartItemForm(request.POST)
        if not form.is_valid():
            messages.error(request, "수정값을 확인해주세요. (수량은 0보다 커야 합니다)")
            return redirect(reverse("inventory:cart"))
        cd = form.cleaned_data
        try:
            update_cart_item(
                user=request.user,
                cart_item_id=kwargs["pk"],
                quantity=cd["quantity"],
                supplier=cd.get("supplier"),
                memo=cd.get("memo", ""),
            )
        except InventoryError as exc:
            messages.error(request, str(exc))
            return redirect(reverse("inventory:cart"))
        messages.success(request, "장바구니 항목을 수정했습니다.")
        return redirect(reverse("inventory:cart"))


class CartItemRemoveView(LoginRequiredMixin, View):
    """장바구니 항목 삭제. POST 전용. (v0.2.0)"""

    def post(self, request, *args, **kwargs):
        try:
            remove_cart_item(user=request.user, cart_item_id=kwargs["pk"])
        except InventoryError as exc:
            messages.error(request, str(exc))
            return redirect(reverse("inventory:cart"))
        messages.success(request, "장바구니에서 삭제했습니다.")
        return redirect(reverse("inventory:cart"))


class OrderConfirmView(LoginRequiredMixin, View):
    """주문 확정 화면. GET=공급업체별 확인, POST=확정. (v0.2.0 / v0.2.2)

    mode=selected 이면 선택한 장바구니 항목(cart_items)만, 그 외에는 전체를 확정한다.
    선택 항목은 본인 장바구니(cart.items) 안에서만 조회되므로 권한 범위는 넓어지지 않는다.
    """

    template_name = "inventory/order_confirm.html"

    def _resolve_ids(self, request):
        src = request.POST if request.method == "POST" else request.GET
        if src.get("mode") == "selected":
            return src.getlist("cart_items")  # 선택 id 목록(빈 리스트 가능)
        return None  # 전체 주문

    def _groups(self, request, ids):
        cart = get_or_create_cart(request.user)
        qs = cart.items.select_related(
            "managed_item", "managed_item__item", "supplier"
        ).order_by("id")
        if ids is not None:
            qs = qs.filter(pk__in=[int(i) for i in ids if str(i).isdigit()])
        items = list(qs)
        groups = {}
        for ci in items:
            groups.setdefault(ci.supplier_id, {"supplier": ci.supplier, "items": []})
            groups[ci.supplier_id]["items"].append(ci)
        return items, list(groups.values())

    def _context(self, request, ids, form):
        items, groups = self._groups(request, ids)
        return {
            "items": items,
            "groups": groups,
            "form": form,
            "has_missing_supplier": any(i.supplier_id is None for i in items),
            "selected_ids": ids if ids is not None else [],
            "mode": "selected" if ids is not None else "all",
        }

    def get(self, request, *args, **kwargs):
        ids = self._resolve_ids(request)
        if ids is not None and len(ids) == 0:
            messages.error(request, "주문할 항목을 선택해주세요.")
            return redirect(reverse("inventory:cart"))
        return render(request, self.template_name, self._context(request, ids, ConfirmOrderForm()))

    def post(self, request, *args, **kwargs):
        ids = self._resolve_ids(request)
        form = ConfirmOrderForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, self._context(request, ids, form))
        cd = form.cleaned_data
        try:
            orders = confirm_order(
                user=request.user,
                order_date=cd.get("order_date"),
                external_order_no=cd.get("external_order_no", ""),
                memo=cd.get("memo", ""),
                cart_item_ids=ids,
            )
        except InventoryError as exc:
            messages.error(request, str(exc))
            return redirect(reverse("inventory:cart"))
        messages.success(
            request,
            f"주문을 확정했습니다. (공급업체별 {len(orders)}건 생성)",
        )
        return redirect(reverse("inventory:order_list"))


class OrderListView(LoginRequiredMixin, ListView):
    """주문 목록. 권한 범위 내 주문. 부서 필터(MANAGER/ADMIN). (v0.2.0 / v0.2.1)"""

    template_name = "inventory/order_list.html"
    context_object_name = "orders"
    paginate_by = 50

    def get_queryset(self):
        self._form = OrderFilterForm(self.request.GET or None, user=self.request.user)
        filters = {}
        if self._form.is_valid():
            cd = self._form.cleaned_data
            for key in ("status", "supplier", "department"):
                if cd.get(key):
                    filters[key] = cd[key]
        return get_orders(self.request.user, filters)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter_form"] = self._form
        return ctx


class OrderDetailView(LoginRequiredMixin, View):
    """주문 상세. OrderItem 별 기입고/잔여 + 입고등록 폼. 권한 밖이면 404. (v0.2.1)"""

    template_name = "inventory/order_detail.html"

    def get(self, request, *args, **kwargs):
        order = get_order_or_none(request.user, kwargs["pk"])
        if order is None:
            raise Http404("주문을 찾을 수 없습니다.")
        return render(
            request,
            self.template_name,
            {
                "order": order,
                "order_items": get_order_items_with_progress(order),
                "can_manage": can_manage_order(request.user, order),
                "today": timezone.localdate(),
            },
        )


class OrderItemStockInView(LoginRequiredMixin, View):
    """주문 품목 기반 입고등록. POST 전용. (v0.2.1)

    실제 재고 증가는 create_stock_in_from_order_item → create_stock_in service 로만.
    """

    def post(self, request, *args, **kwargs):
        order_item = get_order_item_for_user_or_none(request.user, kwargs["pk"])
        if order_item is None:
            raise Http404("주문 품목을 찾을 수 없습니다.")
        detail_url = reverse("inventory:order_detail", args=[order_item.order_id])
        form = OrderItemStockInForm(request.POST)
        if not form.is_valid():
            errs = "; ".join(
                f"{f}: {e[0]}" for f, e in form.errors.items()
            )
            messages.error(request, f"입고등록 값을 확인해주세요. {errs}")
            return redirect(detail_url)
        cd = form.cleaned_data
        try:
            create_stock_in_from_order_item(
                user=request.user,
                order_item=order_item,
                quantity=cd["quantity_input"],
                occurred_at=cd.get("occurred_at"),
                unit_price=cd.get("unit_price"),
                expiration_date=cd.get("expiration_date"),
                no_expiration=cd.get("no_expiration", False),
                memo=cd.get("memo", ""),
            )
        except InventoryError as exc:
            messages.error(request, str(exc))
            return redirect(detail_url)
        messages.success(request, "입고등록이 완료되었습니다. (재고가 증가했습니다)")
        return redirect(detail_url)


class OrderItemCloseView(LoginRequiredMixin, View):
    """미입고 잔여마감. GET=확인 폼, POST=마감. 재고 변경 없음. (v0.2.2)"""

    template_name = "inventory/order_item_close.html"

    def _get_item(self, request, pk):
        oi = get_order_item_for_user_or_none(request.user, pk)
        if oi is None:
            raise Http404("주문 품목을 찾을 수 없습니다.")
        return oi

    def get(self, request, *args, **kwargs):
        oi = self._get_item(request, kwargs["pk"])
        remaining = remaining_quantity(oi)
        return render(
            request,
            self.template_name,
            {
                "oi": oi,
                "remaining": remaining,
                "form": RemainingCloseForm(initial={"quantity": remaining}),
            },
        )

    def post(self, request, *args, **kwargs):
        oi = self._get_item(request, kwargs["pk"])
        detail_url = reverse("inventory:order_detail", args=[oi.order_id])
        form = RemainingCloseForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {"oi": oi, "remaining": remaining_quantity(oi), "form": form},
            )
        cd = form.cleaned_data
        try:
            close_remaining(
                user=request.user,
                order_item=oi,
                quantity=cd["quantity"],
                reason=cd["reason"],
                memo=cd.get("memo", ""),
            )
        except InventoryError as exc:
            messages.error(request, str(exc))
            return redirect(detail_url)
        messages.success(request, "미입고 잔여를 마감 처리했습니다. (현재고는 변경되지 않습니다)")
        return redirect(detail_url)


class InboundPendingListView(LoginRequiredMixin, ListView):
    """입고대기 품목: 잔여수량 > 0 인 OrderItem. 부서 필터(MANAGER/ADMIN). (v0.2.1)"""

    template_name = "inventory/inbound_pending.html"
    context_object_name = "items"
    paginate_by = 50

    def get_queryset(self):
        self._form = InboundPendingFilterForm(
            self.request.GET or None, user=self.request.user
        )
        filters = {}
        if self._form.is_valid():
            cd = self._form.cleaned_data
            for key in ("supplier", "department", "order_date", "overdue"):
                if cd.get(key):
                    filters[key] = cd[key]
        return get_pending_order_items(self.request.user, filters)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter_form"] = self._form
        ctx["today"] = timezone.localdate()
        return ctx


class OrderCancelView(LoginRequiredMixin, View):
    """주문 취소. GET=확인, POST=취소. ORDERED 만 가능. (v0.2.0)"""

    template_name = "inventory/order_cancel.html"

    def _get_order(self, request, pk):
        order = get_order_or_none(request.user, pk)
        if order is None:
            raise Http404("주문을 찾을 수 없습니다.")
        return order

    def get(self, request, *args, **kwargs):
        order = self._get_order(request, kwargs["pk"])
        return render(request, self.template_name, {"order": order})

    def post(self, request, *args, **kwargs):
        order = self._get_order(request, kwargs["pk"])
        try:
            cancel_order(
                user=request.user, order=order,
                reason=request.POST.get("reason", ""),
            )
        except InventoryError as exc:
            messages.error(request, str(exc))
            return redirect(reverse("inventory:order_detail", args=[order.pk]))
        messages.success(request, "주문을 취소했습니다.")
        return redirect(reverse("inventory:order_detail", args=[order.pk]))


# OrderReceiveView(주문 단위 입고완료 버튼)는 v0.2.1 에서 제거되었다.
# 입고등록은 OrderItem 단위(OrderItemStockInView)로만 하며, Order 상태는
# OrderItem 들의 입고 상태를 보고 recompute_order_status 로 자동 갱신된다.


# ---------------------------------------------------------------------------
# 관리자 리포트 / 엑셀 내보내기 (v0.2.4) — MANAGER 이상, 읽기/출력 전용
# ---------------------------------------------------------------------------
class StockExportView(ManagerRequiredMixin, _StockFilterMixin, View):
    """재고현황 엑셀 다운로드. 재고현황 화면과 동일 selector/권한/필터. (v0.2.4)"""

    def get(self, request, *args, **kwargs):
        form = self.get_filter_form()
        filters = self.build_filters(form)
        if request.GET.get("filter") == "low_stock" or request.GET.get("low_stock"):
            filters["low_stock"] = True
        items = get_managed_items_with_current_stock(request.user, filters)
        headers = [
            "부서", "품목명", "규격", "현재고", "최소재고", "단위",
            "기본 공급업체", "보관위치", "활성 여부",
        ]
        rows = (
            [
                mi.department.name,
                mi.item.name,
                mi.item.specification or "",
                mi.current_stock,
                mi.minimum_stock,
                mi.get_unit_display(),
                mi.default_supplier.name if mi.default_supplier_id else "",
                mi.storage_location or "",
                "활성" if mi.is_active else "사용중지",
            ]
            for mi in items
        )
        return xlsx_response(
            filename=dated_filename("inventory_stock_snapshot"),
            sheet_title="재고현황",
            headers=headers,
            rows=rows,
        )


class TransactionExportView(ManagerRequiredMixin, View):
    """거래이력 엑셀 다운로드. 화면 필터/기간 그대로, 페이지네이션 무관 전체. (v0.2.4)"""

    def get(self, request, *args, **kwargs):
        form = TransactionFilterForm(request.GET or None, user=request.user)
        filters = {}
        if form.is_valid():
            cd = form.cleaned_data
            for key in ("department", "transaction_type", "status"):
                if cd.get(key):
                    filters[key] = cd[key]
        date_from, date_to = resolve_tx_date_range(request.GET)
        qs = get_export_transactions(request.user, filters, date_from, date_to)
        headers = [
            "거래일자", "거래유형", "상태", "부서", "품목명", "수량", "단가",
            "유통기한", "공급업체", "입력자", "승인자", "메모", "주문연계",
        ]
        rows = (
            [
                timezone.localdate(t.occurred_at),
                t.get_transaction_type_display(),
                t.get_status_display(),
                t.managed_item.department.name,
                t.managed_item.item.name,
                t.quantity_delta,
                t.unit_price if t.unit_price is not None else "",
                t.expiration_date if t.expiration_date else "",
                t.supplier.name if t.supplier_id else "",
                t.created_by.display_name,
                t.approved_by.display_name if t.approved_by_id else "",
                t.memo or "",
                "주문연계" if t.source_order_item_id else "",
            ]
            for t in qs
        )
        return xlsx_response(
            filename=dated_filename("inventory_transactions"),
            sheet_title="거래이력",
            headers=headers,
            rows=rows,
        )


class InboundPendingExportView(ManagerRequiredMixin, View):
    """입고대기 품목 엑셀 다운로드. 미처리잔여 > 0 인 OrderItem 만. (v0.2.4)"""

    def get(self, request, *args, **kwargs):
        form = InboundPendingFilterForm(request.GET or None, user=request.user)
        filters = {}
        if form.is_valid():
            cd = form.cleaned_data
            for key in ("supplier", "department", "order_date", "overdue"):
                if cd.get(key):
                    filters[key] = cd[key]
        items = get_pending_order_items(request.user, filters)
        headers = [
            "주문번호", "주문일자", "공급업체", "부서", "품목명",
            "주문수량", "기입고수량", "잔여수량", "잔여마감수량", "상태", "주문자",
        ]
        rows = (
            [
                oi.order.internal_order_no,
                oi.order.order_date,
                oi.order.supplier.name,
                oi.managed_item.department.name,
                oi.managed_item.item.name,
                oi.quantity,
                oi.received_qty,
                oi.remaining_qty,
                oi.remaining_closed_quantity,
                oi.order.get_status_display(),
                oi.order.ordered_by.display_name,
            ]
            for oi in items
        )
        return xlsx_response(
            filename=dated_filename("inventory_inbound_pending"),
            sheet_title="입고대기 품목",
            headers=headers,
            rows=rows,
        )


class _MonthlyReportMixin:
    """월간 입출고 요약: 폼/기간/요약행 구성 공통 로직."""

    def _build(self, request):
        form = MonthlyReportForm(request.GET or None)
        today = timezone.localdate()
        start = end = None
        filters = {}
        if form.is_valid():
            cd = form.cleaned_data
            start = cd.get("start_date")
            end = cd.get("end_date")
            if cd.get("department"):
                filters["department"] = cd["department"]
            if cd.get("supplier"):
                filters["supplier"] = cd["supplier"]
            if cd.get("item_query"):
                filters["item_query"] = cd["item_query"]
        if start is None:
            start = today.replace(day=1)
        if end is None:
            end = today
        rows = get_monthly_summary(request.user, start, end, filters)
        return form, start, end, rows


class MonthlyReportView(ManagerRequiredMixin, _MonthlyReportMixin, View):
    """월간 입출고 요약 리포트 화면. (v0.2.4)"""

    template_name = "inventory/monthly_report.html"

    def get(self, request, *args, **kwargs):
        form, start, end, rows = self._build(request)
        totals = {
            "in_qty": sum((r["in_qty"] for r in rows), Decimal("0")),
            "out_qty": sum((r["out_qty"] for r in rows), Decimal("0")),
            "net": sum((r["net"] for r in rows), Decimal("0")),
            "in_amount": sum((r["in_amount"] for r in rows), Decimal("0")),
        }
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "rows": rows,
                "totals": totals,
                "start": start,
                "end": end,
            },
        )


class MonthlyReportExportView(ManagerRequiredMixin, _MonthlyReportMixin, View):
    """월간 입출고 요약 엑셀 다운로드. (v0.2.4)"""

    def get(self, request, *args, **kwargs):
        _form, start, end, rows = self._build(request)
        headers = [
            "부서", "품목명", "입고수량", "출고수량", "순증감",
            "입고금액", "최근 입고일", "최근 출고일",
        ]
        out_rows = (
            [
                r["department"],
                r["item_name"],
                r["in_qty"],
                r["out_qty"],
                r["net"],
                r["in_amount"],
                timezone.localdate(r["last_in"]) if r["last_in"] else "",
                timezone.localdate(r["last_out"]) if r["last_out"] else "",
            ]
            for r in rows
        )
        return xlsx_response(
            filename=dated_filename("inventory_monthly_report"),
            sheet_title="월간 입출고 요약",
            headers=headers,
            rows=out_rows,
        )


# ---------------------------------------------------------------------------
# 관리자 기준정보 점검 / 기준정보 엑셀 (v0.2.5) — MANAGER 이상, 읽기·출력 전용
# ---------------------------------------------------------------------------
class MasterDataCheckView(ManagerRequiredMixin, View):
    """기준정보 점검 화면. command/엑셀과 동일한 master_data_checks 로직 재사용. (v0.2.5)"""

    template_name = "inventory/master_data_check.html"

    def get(self, request, *args, **kwargs):
        result = run_master_data_checks()
        return render(request, self.template_name, {"result": result})


class MasterDataCheckExportView(ManagerRequiredMixin, View):
    """기준정보 엑셀 다운로드 (관리품목/품목/공급업체/점검결과 시트). (v0.2.5)"""

    def get(self, request, *args, **kwargs):
        result = run_master_data_checks()

        mi_headers = [
            "부서", "품목명", "규격", "단위", "관리품목 활성 여부", "현재고",
            "최소재고", "기본 공급업체", "보관위치", "최초재고 입력 여부", "점검 상태", "비고",
        ]
        mi_rows = [
            [
                r["department"], r["item_name"], r["specification"], r["unit"],
                r["is_active"], r["current_stock"], r["minimum_stock"],
                r["default_supplier"], r["storage_location"], r["has_initial"],
                r["status"], "",
            ]
            for r in managed_item_rows(result)
        ]

        item_headers = ["품목명", "규격", "분류", "활성 여부", "연결된 관리품목 수", "비고"]
        item_data = [
            [r["name"], r["specification"], r["category"], r["is_active"], r["managed_count"], ""]
            for r in item_rows()
        ]

        sup_headers = ["공급업체명", "활성 여부", "연락처", "메모", "기본공급 관리품목 수", "비고"]
        sup_data = [
            [r["name"], r["is_active"], r["phone"], r["memo"], r["default_count"], ""]
            for r in supplier_rows()
        ]

        check_headers = ["점검구분", "심각도", "부서", "품목명", "내용", "권장조치", "관리품목 ID"]
        check_data = [
            [f["section"], f["severity"], f["dept"], f["item_name"],
             f["message"], f["recommend"], f["mi_id"]]
            for f in result["findings"]
        ]

        return xlsx_multi_sheet_response(
            filename=dated_filename("inventory_master_data_check"),
            sheets=[
                ("관리품목", mi_headers, mi_rows),
                ("품목", item_headers, item_data),
                ("공급업체", sup_headers, sup_data),
                ("점검결과", check_headers, check_data),
            ],
        )
