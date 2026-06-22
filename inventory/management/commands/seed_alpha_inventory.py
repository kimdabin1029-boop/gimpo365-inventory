"""알파테스트용 기본 재고 데이터 생성 (DEBUG 전용 seed).

주의:
- 실제 운영 데이터 세팅용이 아니라 "알파테스트용 샘플 데이터" 생성 도구다.
- 운영(DEBUG=False) 환경에서는 무조건 실행을 거부한다.
- 초기재고/거래 생성은 반드시 기존 service(request_initial_count / create_stock_*) 를 사용한다.
  StockTransaction 을 직접 create 하지 않는다. (TECH_SPEC §0)
- 모델/마이그레이션/Admin/PROTECT/service/selector/form/view 를 변경하지 않는다.
- 생성하는 테스트 사용자/공급업체/품목은 reset_alpha_data 와 호환되도록
  username 은 _test 접미, 공급업체/품목명은 [테스트] prefix 를 사용한다.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from datetime import timedelta

from django.utils import timezone

from accounts.models import Role
from core.models import Department
from inventory.models import (
    Item,
    ItemCategory,
    ManagedItem,
    StockTransaction,
    Supplier,
    TransactionType,
    Unit,
)
from inventory.selectors import get_current_stock, has_approved_initial_count
from inventory.services import (
    create_stock_in,
    create_stock_out,
    request_initial_count,
)

User = get_user_model()

# 과거 거래(--with-history): (태그, 거래유형, 수량, 며칠 전). 같은 날은 IN 을 먼저 둔다.
HISTORY_ENTRIES = [
    ("in-3d", TransactionType.IN, 5, 3),
    ("out-3d", TransactionType.OUT_USE, 2, 3),
    ("in-10d", TransactionType.IN, 5, 10),
    ("out-10d", TransactionType.OUT_USE, 2, 10),
    ("in-35d", TransactionType.IN, 5, 35),    # 지난달
    ("in-100d", TransactionType.IN, 5, 100),  # 최근 3개월 밖
]

CONFIRM_WORD = "SEED"
PASSWORD = "test1234!"  # 알파테스트 계정 공통 비밀번호 (문서에 명시)

# 기본 부서 (항상 보장; 이미 있으면 재사용)
DEPT_DEFS = [
    ("피부실", True),
    ("치료실", True),
    ("탕전실", False),
]

# 공급업체 ([테스트] prefix)
SUP_COMMON = "[테스트] 공통소모품 거래처"
SUP_SKIN = "[테스트] 피부소모품 거래처"
SUP_TREATMENT = "[테스트] 치료실소모품 거래처"

# 부서 키 → (Department name, 테스트 사용자들[(username, role)], 공급업체)
DEPT_KEY = {
    "skin": "피부실",
    "treatment": "치료실",
}
USERS_BY_DEPT = {
    "skin": [("skin_staff_test", Role.STAFF), ("skin_leader_test", Role.TEAM_LEADER)],
    "treatment": [
        ("treatment_staff_test", Role.STAFF),
        ("treatment_leader_test", Role.TEAM_LEADER),
    ],
}

# 공유 품목(부서 간 동일 물리 품목): Item 1개 + 부서별 ManagedItem
_SHARED = {"[테스트] 알코올솜", "[테스트] 장갑"}

# 품목/관리품목 계획: name, category, unit, minimum_stock, initial(None=초기재고 없음)
ITEM_PLAN = {
    "skin": [
        ("[테스트] 알코올솜", ItemCategory.HYGIENE_SUPPLY, Unit.EA, 10, 50),
        ("[테스트] 니들 30G", ItemCategory.MEDICAL_SUPPLY, Unit.EA, 10, 10),
        ("[테스트] 마스크팩", ItemCategory.BEAUTY_SUPPLY, Unit.EA, 10, 3),
        ("[테스트] 필링제", ItemCategory.BEAUTY_SUPPLY, Unit.BOTTLE, 5, None),
        ("[테스트] 앰플", ItemCategory.BEAUTY_SUPPLY, Unit.EA, 10, 50),
        ("[테스트] 소독젤", ItemCategory.HYGIENE_SUPPLY, Unit.BOTTLE, 5, 8),
        ("[테스트] 일회용 시트", ItemCategory.HYGIENE_SUPPLY, Unit.EA, 20, 100),
        ("[테스트] 장갑", ItemCategory.HYGIENE_SUPPLY, Unit.BOX, 5, 10),
        ("[테스트] 거즈 5x5", ItemCategory.MEDICAL_SUPPLY, Unit.EA, 10, 3),
        ("[테스트] 드레싱재", ItemCategory.MEDICAL_SUPPLY, Unit.EA, 10, 50),
    ],
    "treatment": [
        ("[테스트] 침 0.25x30", ItemCategory.MEDICAL_SUPPLY, Unit.BOX, 10, 50),
        ("[테스트] 침 0.30x40", ItemCategory.MEDICAL_SUPPLY, Unit.BOX, 10, 10),
        ("[테스트] 부항컵", ItemCategory.MEDICAL_SUPPLY, Unit.EA, 10, 3),
        ("[테스트] 알코올솜", ItemCategory.HYGIENE_SUPPLY, Unit.EA, 10, 50),
        ("[테스트] 핫팩커버", ItemCategory.GENERAL_SUPPLY, Unit.EA, 10, None),
        ("[테스트] 일회용 베개커버", ItemCategory.HYGIENE_SUPPLY, Unit.EA, 20, 100),
        ("[테스트] 장갑", ItemCategory.HYGIENE_SUPPLY, Unit.BOX, 5, 10),
        ("[테스트] 거즈 10x10", ItemCategory.MEDICAL_SUPPLY, Unit.EA, 10, 3),
        ("[테스트] 테이핑", ItemCategory.MEDICAL_SUPPLY, Unit.ROLL, 5, 8),
        ("[테스트] 소독제", ItemCategory.HYGIENE_SUPPLY, Unit.BOTTLE, 5, None),
    ],
}


class Command(BaseCommand):
    help = (
        "알파테스트용 기본 재고 데이터 생성 (DEBUG 전용). "
        "부서/테스트 사용자/공급업체/품목/관리품목/초기재고 샘플을 idempotent 하게 만든다. "
        "운영 환경에서는 실행되지 않는다."
    )

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="확인 프롬프트(SEED 입력) 생략")
        parser.add_argument("--dry-run", action="store_true", help="실제 생성 없이 예정 데이터/건수만 표시")
        parser.add_argument(
            "--department",
            choices=["skin", "treatment", "all"],
            default="all",
            help="대상 부서 (기본: all)",
        )
        parser.add_argument(
            "--with-transactions",
            action="store_true",
            help="입고/출고 샘플 거래(당일)도 생성 (service 사용, [seed] 메모로 idempotent)",
        )
        parser.add_argument(
            "--with-history",
            action="store_true",
            help=(
                "과거 거래이력도 생성 (기간 필터/과거 취소 제한 확인용). "
                "service 로 생성 후 seed 거래의 created_at 만 과거값으로 보정한다(DEBUG 전용 예외)."
            ),
        )

    # -- helpers --
    def _selected(self, dept_opt):
        return ["skin", "treatment"] if dept_opt == "all" else [dept_opt]

    def _supplier_for(self, dept_key, item_name):
        if item_name in _SHARED:
            return SUP_COMMON
        return SUP_SKIN if dept_key == "skin" else SUP_TREATMENT

    def handle(self, *args, **options):
        # 가드: 운영(DEBUG=False)에서는 무조건 중단
        if not settings.DEBUG:
            raise CommandError(
                "DEBUG=False 환경에서는 실행할 수 없습니다. (운영 데이터 보호 — 알파테스트 전용 seed)"
            )

        dry_run = options["dry_run"]
        selected = self._selected(options["department"])
        with_tx = options["with_transactions"]
        with_history = options["with_history"]

        if dry_run:
            self._dry_run(selected, with_tx, with_history)
            return

        if not options["yes"]:
            answer = input(f"알파테스트 샘플 데이터를 생성하려면 '{CONFIRM_WORD}' 를 입력하세요: ")
            if answer.strip() != CONFIRM_WORD:
                raise CommandError("확인 문자열이 일치하지 않아 취소되었습니다.")

        c = {
            "dept_new": 0, "dept_reuse": 0,
            "user_new": 0, "user_reuse": 0,
            "sup_new": 0, "sup_reuse": 0,
            "item_new": 0, "item_reuse": 0,
            "mi_new": 0, "mi_reuse": 0,
            "initial_created": 0, "initial_skipped": 0,
            "tx_created": 0,
            "history_created": 0, "history_skipped": 0,
        }

        # 1) 부서 (항상 3개 보장)
        dept_objs = {}
        for name, afi in DEPT_DEFS:
            obj, created = Department.objects.get_or_create(
                name=name, defaults={"active_for_inventory": afi}
            )
            dept_objs[name] = obj
            c["dept_new" if created else "dept_reuse"] += 1

        # 2) 공급업체 (공통 + 선택 부서)
        sup_names = {SUP_COMMON}
        if "skin" in selected:
            sup_names.add(SUP_SKIN)
        if "treatment" in selected:
            sup_names.add(SUP_TREATMENT)
        sup_objs = {}
        for sname in sup_names:
            obj, created = Supplier.objects.get_or_create(name=sname)
            sup_objs[sname] = obj
            c["sup_new" if created else "sup_reuse"] += 1

        # 3) 사용자: manager_test(항상) + 선택 부서 사용자
        manager = self._ensure_user("manager_test", Role.MANAGER, None, c)
        for dept_key in selected:
            dept = dept_objs[DEPT_KEY[dept_key]]
            for username, role in USERS_BY_DEPT[dept_key]:
                self._ensure_user(username, role, dept, c)

        # 4) 품목/관리품목/초기재고
        for dept_key in selected:
            dept = dept_objs[DEPT_KEY[dept_key]]
            for name, cat, unit, min_stock, initial in ITEM_PLAN[dept_key]:
                item, item_created = Item.objects.get_or_create(
                    name=name, defaults={"category": cat}
                )
                c["item_new" if item_created else "item_reuse"] += 1

                supplier = sup_objs[self._supplier_for(dept_key, name)]
                mi, mi_created = ManagedItem.objects.get_or_create(
                    item=item,
                    department=dept,
                    defaults={
                        "unit": unit,
                        "minimum_stock": min_stock,
                        "storage_location": f"{dept.name} 수납장",
                        "default_supplier": supplier,
                    },
                )
                c["mi_new" if mi_created else "mi_reuse"] += 1

                # 초기재고: 기존 service 로 생성 (MANAGER → 즉시 APPROVED)
                if initial is not None:
                    if has_approved_initial_count(mi):
                        c["initial_skipped"] += 1
                    else:
                        request_initial_count(
                            user=manager, managed_item=mi, quantity=initial,
                            memo="[seed]",
                        )
                        c["initial_created"] += 1

        # 5) (옵션) 샘플 거래 — service 사용, [seed] 메모로 idempotent
        if with_tx:
            for dept_key in selected:
                dept = dept_objs[DEPT_KEY[dept_key]]
                staff_username = USERS_BY_DEPT[dept_key][0][0]
                staff = User.objects.get(username=staff_username)
                # 재고가 충분한 첫 관리품목 선택
                mi = (
                    ManagedItem.objects.filter(department=dept)
                    .order_by("id")
                    .first()
                )
                if mi and get_current_stock(mi) >= 2:
                    if not mi.stock_transactions.filter(
                        transaction_type=TransactionType.IN, memo="[seed]"
                    ).exists():
                        create_stock_in(user=staff, managed_item=mi, quantity=5, memo="[seed]")
                        c["tx_created"] += 1
                    if not mi.stock_transactions.filter(
                        transaction_type=TransactionType.OUT_USE, memo="[seed]"
                    ).exists():
                        create_stock_out(
                            user=staff, managed_item=mi,
                            transaction_type=TransactionType.OUT_USE, quantity=2,
                            memo="[seed]",
                        )
                        c["tx_created"] += 1

        # 6) (옵션) 과거 거래이력 — service 로 생성 후 created_at 만 과거값으로 보정
        if with_history:
            for dept_key in selected:
                self._seed_history(dept_key, dept_objs, c)

        self._print_summary(c, with_tx, with_history)

    def _seed_history(self, dept_key, dept_objs, c):
        """과거 거래이력 생성. service 로 생성한 뒤 seed 거래의 created_at 만 과거로 update.

        (DEBUG 전용 알파테스트 데이터 시간 보정 — 운영 로직에서는 created_at 을 조작하지 않는다.
         status 직접 변경/StockTransaction 직접 create 는 하지 않는다.)
        """
        dept = dept_objs[DEPT_KEY[dept_key]]
        staff = User.objects.get(username=USERS_BY_DEPT[dept_key][0][0])
        # 승인 초기재고(=재고 보유)가 있는 첫 관리품목 선택
        mi = (
            ManagedItem.objects.filter(department=dept).order_by("id").first()
        )
        if not mi or not has_approved_initial_count(mi):
            return

        for tag, ttype, qty_val, days_ago in HISTORY_ENTRIES:
            memo = f"[seed-history] {tag}"
            if mi.stock_transactions.filter(memo=memo).exists():
                c["history_skipped"] += 1
                continue
            occurred = timezone.now() - timedelta(days=days_ago)
            if ttype == TransactionType.IN:
                tx = create_stock_in(
                    user=staff, managed_item=mi, quantity=qty_val,
                    occurred_at=occurred, memo=memo,
                )
            else:
                if get_current_stock(mi) < qty_val:
                    c["history_skipped"] += 1
                    continue
                tx = create_stock_out(
                    user=staff, managed_item=mi,
                    transaction_type=ttype, quantity=qty_val,
                    occurred_at=occurred, memo=memo,
                )
            # seed 전용: created_at(입력일시)도 과거로 보정 → 과거 취소 제한 확인 가능
            StockTransaction.objects.filter(pk=tx.pk).update(created_at=occurred)
            c["history_created"] += 1

    def _ensure_user(self, username, role, department, c):
        obj, created = User.objects.get_or_create(
            username=username, defaults={"role": role, "department": department}
        )
        if created:
            obj.role = role
            obj.department = department
            obj.set_password(PASSWORD)
            obj.save()
            c["user_new"] += 1
        else:
            c["user_reuse"] += 1
        return obj

    def _print_summary(self, c, with_tx, with_history=False):
        self.stdout.write(self.style.SUCCESS("알파테스트 시드 완료. 요약:"))
        self.stdout.write(f"  - 부서: 신규 {c['dept_new']} / 재사용 {c['dept_reuse']}")
        self.stdout.write(f"  - 사용자: 신규 {c['user_new']} / 재사용 {c['user_reuse']}")
        self.stdout.write(f"  - 공급업체: 신규 {c['sup_new']} / 재사용 {c['sup_reuse']}")
        self.stdout.write(f"  - 품목: 신규 {c['item_new']} / 재사용 {c['item_reuse']}")
        self.stdout.write(f"  - 관리품목: 신규 {c['mi_new']} / 재사용 {c['mi_reuse']}")
        self.stdout.write(
            f"  - 초기재고: 생성 {c['initial_created']} / 스킵 {c['initial_skipped']}"
        )
        if with_tx:
            self.stdout.write(f"  - 샘플 거래(당일): 생성 {c['tx_created']}")
        if with_history:
            self.stdout.write(
                f"  - 과거 거래이력: 생성 {c['history_created']} / 스킵 {c['history_skipped']}"
            )
        self.stdout.write(f"  - 테스트 계정 비밀번호: {PASSWORD}")

    def _dry_run(self, selected, with_tx, with_history=False):
        self.stdout.write("[dry-run] 생성 예정 (실제 생성하지 않음):")

        def cnt(model, names, field="name"):
            new = sum(
                0 if model.objects.filter(**{field: n}).exists() else 1 for n in names
            )
            return new, len(names) - new

        d_new, d_old = cnt(Department, [n for n, _ in DEPT_DEFS])
        self.stdout.write(f"  - 부서: 신규 {d_new} / 기존 {d_old}")

        usernames = ["manager_test"]
        for k in selected:
            usernames += [u for u, _ in USERS_BY_DEPT[k]]
        u_new, u_old = cnt(User, usernames, field="username")
        self.stdout.write(f"  - 사용자: 신규 {u_new} / 기존 {u_old}  ({', '.join(usernames)})")

        sups = {SUP_COMMON}
        if "skin" in selected:
            sups.add(SUP_SKIN)
        if "treatment" in selected:
            sups.add(SUP_TREATMENT)
        s_new, s_old = cnt(Supplier, list(sups))
        self.stdout.write(f"  - 공급업체: 신규 {s_new} / 기존 {s_old}")

        item_names = []
        managed_pairs = 0
        initials = 0
        for k in selected:
            for name, cat, unit, mn, init in ITEM_PLAN[k]:
                item_names.append(name)
                managed_pairs += 1
                if init is not None:
                    initials += 1
        uniq_items = list(dict.fromkeys(item_names))
        i_new, i_old = cnt(Item, uniq_items)
        self.stdout.write(f"  - 품목(고유): 신규 {i_new} / 기존 {i_old} (총 {len(uniq_items)})")
        self.stdout.write(f"  - 관리품목(부서×품목): {managed_pairs} (이미 존재 시 재사용)")
        self.stdout.write(f"  - 초기재고 생성 예정(최대): {initials} (APPROVED 존재 시 스킵)")
        if with_tx:
            self.stdout.write(f"  - 샘플 거래(당일): 선택 부서당 입고1/출고1 (이미 [seed] 있으면 스킵)")
        if with_history:
            self.stdout.write(
                f"  - 과거 거래이력: 선택 부서당 최대 {len(HISTORY_ENTRIES)}건 "
                f"(3/10/35/100일 전, [seed-history] 있으면 스킵)"
            )
        self.stdout.write(self.style.WARNING("[dry-run] 실제 생성 없음."))
