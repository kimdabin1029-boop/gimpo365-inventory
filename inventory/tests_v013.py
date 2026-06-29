"""v0.1.3 알파 사용성 핫픽스 테스트.

- 거래이력 메모 tooltip(아이콘) + 거래 상세 전체 메모 유지
- 좌측 퀵메뉴(사이드바): 이동 링크 / active / 권한별 노출
- 대시보드 최소재고 이하 목록(권한 범위, 최대 8건, 재고현황 링크)
- 승인대기 큐 전체선택 체크박스
"""

from django.urls import reverse

from core.factories import (
    BaseFixtureTestCase,
    approve_initial_count,
    create_item,
    create_managed_item,
)
from inventory.models import ItemCategory
from inventory.services import create_stock_in, request_initial_count


class TransactionMemoTooltipTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)
        approve_initial_count(cls.mi, created_by=cls.manager)
        cls.tx_memo = create_stock_in(
            user=cls.staff_skin, managed_item=cls.mi, quantity=10,
            memo="로트번호 A-123 / 유통기한 확인 요망",
        )
        cls.tx_plain = create_stock_in(
            user=cls.staff_skin, managed_item=cls.mi, quantity=5, memo="",
        )

    # 1. 메모 있는 거래에 아이콘 + tooltip(title)
    def test_memo_icon_shown_with_title(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:transaction_list"))
        self.assertContains(resp, "memo-icon")
        self.assertContains(resp, 'title="로트번호 A-123 / 유통기한 확인 요망"')

    # 3. 메모 없는 거래는 아이콘 없음 (정확히 1개만)
    def test_no_memo_icon_for_plain_transaction(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:transaction_list"))
        self.assertEqual(resp.content.decode().count("memo-icon"), 1)

    # 2. 거래 상세에서 전체 메모 계속 확인 가능
    def test_detail_still_shows_full_memo(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(
            reverse("inventory:transaction_detail", args=[self.tx_memo.pk])
        )
        self.assertContains(resp, "로트번호 A-123 / 유통기한 확인 요망")


class SidebarQuickMenuTest(BaseFixtureTestCase):
    # 4. 주요 페이지 이동 링크
    def test_sidebar_has_core_links(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:dashboard"))
        for name in ("dashboard", "stock_list", "stock_in_new", "stock_out_new", "transaction_list"):
            self.assertContains(resp, reverse(f"inventory:{name}"))

    # 5. 현재 페이지 active 표시
    def test_active_state_on_current_page(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:dashboard"))
        self.assertContains(
            resp, f'aria-current="page" href="{reverse("inventory:dashboard")}"'
        )

    def test_active_state_follows_page(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:stock_in_new"))
        self.assertContains(
            resp, f'aria-current="page" href="{reverse("inventory:stock_in_new")}"'
        )

    # 6. STAFF 에게 관리자용(승인대기) 메뉴 미노출
    def test_staff_does_not_see_manager_menu(self):
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:dashboard"))
        # 사이드바 승인대기 링크(클래스 포함)가 STAFF 에게는 없어야 한다.
        self.assertNotContains(
            resp,
            f'class="sidebar-link" href="{reverse("inventory:pending_list")}"',
        )
        # 실사조정도 STAFF(권한 없음)에게는 사이드바에 없어야 한다.
        self.assertNotContains(
            resp,
            f'class="sidebar-link" href="{reverse("inventory:adjustment_new")}"',
        )

    def test_team_leader_sees_adjustment_not_pending(self):
        self.client.force_login(self.team_leader_skin)
        resp = self.client.get(reverse("inventory:dashboard"))
        self.assertContains(resp, reverse("inventory:adjustment_new"))
        self.assertNotContains(
            resp,
            f'class="sidebar-link" href="{reverse("inventory:pending_list")}"',
        )

    def test_manager_sees_pending_menu(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:dashboard"))
        self.assertContains(resp, reverse("inventory:pending_list"))


class DashboardLowStockTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.cat = ItemCategory.MEDICAL_SUPPLY

    def _low_item(self, name, *, dept, minimum, initial):
        item = create_item(name, category=self.cat)
        mi = create_managed_item(
            item=item, department=dept, minimum_stock=minimum
        )
        approve_initial_count(mi, created_by=self.manager, quantity=initial)
        return mi

    # 7. 대시보드에 최소재고 이하 품목 표시
    def test_low_stock_items_shown(self):
        self._low_item("거즈 5x5", dept=self.dept_skin, minimum=5, initial=0)  # 재고없음
        self._low_item("니들 30G", dept=self.dept_skin, minimum=5, initial=3)  # 최소재고 이하
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:dashboard"))
        self.assertContains(resp, "거즈 5x5")
        self.assertContains(resp, "재고없음")
        self.assertContains(resp, "최소재고 이하")

    # 8. 항목이 많아도 대시보드에는 최대 8건만
    def test_low_stock_capped_at_limit(self):
        for i in range(12):
            self._low_item(f"품목{i:02d}", dept=self.dept_skin, minimum=5, initial=0)
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:dashboard"))
        self.assertLessEqual(len(resp.context["low_stock_items"]), 8)
        self.assertContains(resp, "외")  # "외 N건 더 있음"

    # 9. 재고현황으로 이동 링크
    def test_link_to_stock_list(self):
        self._low_item("거즈 5x5", dept=self.dept_skin, minimum=5, initial=0)
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:dashboard"))
        self.assertContains(resp, reverse("inventory:stock_list"))

    # 권한 범위: STAFF 는 타 부서 최소재고 품목을 보지 않는다.
    def test_low_stock_scoped_to_permission(self):
        self._low_item("치료실품목", dept=self.dept_treatment, minimum=5, initial=0)
        self.client.force_login(self.staff_skin)  # 피부실 STAFF
        resp = self.client.get(reverse("inventory:dashboard"))
        self.assertNotContains(resp, "치료실품목")


class PendingSelectAllTest(BaseFixtureTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.item = create_item("거즈 5x5", category=ItemCategory.MEDICAL_SUPPLY)
        cls.mi = create_managed_item(item=cls.item, department=cls.dept_skin)
        # PENDING 초기재고 1건 (일괄 승인 대상)
        request_initial_count(
            user=cls.team_leader_skin, managed_item=cls.mi, quantity=20
        )

    # 10/11. 전체선택 체크박스 노출 (manager) + 폼에 보이는 항목 체크박스 존재
    def test_select_all_checkbox_present(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse("inventory:pending_list"))
        self.assertContains(resp, 'id="bulk-select-all"')
        # 보이는 PENDING 초기재고에 대한 선택 체크박스가 폼에 렌더된다.
        self.assertContains(resp, 'name="selected"')

    def test_staff_cannot_access_pending(self):
        # 승인대기 화면 자체가 manager 전용(권한 범위 미변경 확인)
        self.client.force_login(self.staff_skin)
        resp = self.client.get(reverse("inventory:pending_list"))
        self.assertEqual(resp.status_code, 403)
