"""알파테스트용 재고 데이터 초기화 (DEBUG 전용 teardown).

주의:
- 이 명령은 "운영 데이터 정정" 기능이 아니다. 알파테스트 데이터를 비우는 비운영 teardown 이다.
- 운영(DEBUG=False) 환경에서는 무조건 실행을 거부한다.
- Admin 의 StockTransaction 삭제 권한이나 PROTECT FK, service 계층은 전혀 변경하지 않는다.
  (이 명령은 자식→부모 순서로 ORM 삭제하므로 PROTECT 를 깨지 않는다.)

기본 동작: StockTransaction → ManagedItem → Item → Supplier 삭제.
유지: Department(전체), User(전체), superuser/ADMIN.
사용자 삭제는 --delete-test-users 옵션으로만, 그것도 test_ 접두/_test 접미 + superuser/ADMIN 제외.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from accounts.models import Role
from inventory.models import Item, ManagedItem, StockTransaction, Supplier

User = get_user_model()

CONFIRM_WORD = "RESET"


class Command(BaseCommand):
    help = (
        "알파테스트용 재고 데이터 초기화 (DEBUG 전용). "
        "기본: StockTransaction/ManagedItem/Item/Supplier 삭제, 사용자·부서 유지. "
        "운영 환경에서는 실행되지 않는다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help="확인 프롬프트(RESET 입력) 생략",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="실제 삭제 없이 삭제 대상/건수만 표시",
        )
        parser.add_argument(
            "--delete-test-users",
            action="store_true",
            help=(
                "username 이 test_ 로 시작하거나 _test 로 끝나는 사용자 삭제. "
                "superuser / ADMIN 계정은 어떤 경우에도 삭제하지 않음."
            ),
        )

    def _test_users_qs(self):
        # 테스트 계정 한정 + superuser/ADMIN 절대 제외
        return (
            User.objects.filter(
                Q(username__startswith="test_") | Q(username__endswith="_test")
            )
            .exclude(is_superuser=True)
            .exclude(role=Role.ADMIN)
        )

    def handle(self, *args, **options):
        # 가드 1: 운영(DEBUG=False)에서는 무조건 중단
        if not settings.DEBUG:
            raise CommandError(
                "DEBUG=False 환경에서는 실행할 수 없습니다. "
                "(운영 데이터 보호 — 알파테스트 전용 명령)"
            )

        dry_run = options["dry_run"]
        delete_test_users = options["delete_test_users"]

        targets = {
            "StockTransaction": StockTransaction.objects.count(),
            "ManagedItem": ManagedItem.objects.count(),
            "Item": Item.objects.count(),
            "Supplier": Supplier.objects.count(),
        }
        test_users_qs = self._test_users_qs()
        if delete_test_users:
            targets["TestUsers"] = test_users_qs.count()

        self.stdout.write("초기화 대상 (삭제 예정):")
        for name, n in targets.items():
            self.stdout.write(f"  - {name}: {n}")
        self.stdout.write(
            "유지: Department(전체), User(전체), superuser/ADMIN"
            + ("" if delete_test_users else "  (사용자 유지 — --delete-test-users 미사용)")
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("[dry-run] 실제 삭제를 수행하지 않았습니다."))
            return

        # 가드 2: --yes 없으면 RESET 입력 요구
        if not options["yes"]:
            answer = input(f"정말 초기화하려면 '{CONFIRM_WORD}' 를 입력하세요: ")
            if answer.strip() != CONFIRM_WORD:
                raise CommandError("확인 문자열이 일치하지 않아 취소되었습니다.")

        deleted = {}
        # 자식 → 부모 순서로 삭제 (PROTECT 안전)
        with transaction.atomic():
            deleted["StockTransaction"] = StockTransaction.objects.all().delete()[0]
            deleted["ManagedItem"] = ManagedItem.objects.all().delete()[0]
            deleted["Item"] = Item.objects.all().delete()[0]
            deleted["Supplier"] = Supplier.objects.all().delete()[0]
            if delete_test_users:
                # 거래가 먼저 삭제되어 created_by 등 PROTECT 참조가 해제된 뒤 삭제
                deleted["TestUsers"] = test_users_qs.delete()[0]

        self.stdout.write(self.style.SUCCESS("초기화 완료. 삭제 건수:"))
        for name, n in deleted.items():
            self.stdout.write(f"  - {name}: {n}")
