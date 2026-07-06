"""운영 시작 전 운영기록 초기화 (기준정보는 유지). (v0.2.5)

목적:
- 직원교육/알파테스트 후 정식 운영 시작 전에, 기준정보(User/Department/Supplier/Item/
  ManagedItem/보관위치/최소재고/기본공급업체/단위/규격/권한)는 유지하고
  운영기록(StockTransaction/Order/OrderItem/CartItem)만 삭제한다.

안전장치:
- 기본 실행은 dry-run (삭제 예정 건수만 출력).
- 실제 삭제는 --yes 에서만 수행.
- DEBUG=False(운영) 환경에서는 --allow-production 없이는 실행 차단.
- transaction.atomic 으로 일괄 삭제.

주의: StockTransaction 을 삭제하면 현재고 기준(APPROVED 합계)도 사라진다.
정식 운영 시작 전 관리품목별 최초재고 입력/승인이 필요하다.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Department
from inventory.models import (
    CartItem,
    Item,
    ManagedItem,
    Order,
    OrderItem,
    StockTransaction,
    Supplier,
)

User = get_user_model()


class Command(BaseCommand):
    help = (
        "운영기록(StockTransaction/Order/OrderItem/CartItem)만 삭제하고 기준정보는 유지한다. "
        "기본은 dry-run, --yes 에서만 실제 삭제. DEBUG=False 에서는 --allow-production 필요."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes", action="store_true",
            help="실제 삭제 수행. (미지정 시 dry-run)",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="삭제하지 않고 예정 건수만 출력. (기본 동작)",
        )
        parser.add_argument(
            "--allow-production", action="store_true",
            help="DEBUG=False(운영) 환경에서도 실행 허용 (--yes 와 함께).",
        )

    def handle(self, *args, **options):
        do_delete = options["yes"] and not options["dry_run"]

        # 운영기록 삭제 대상 / 기준정보(유지) 건수
        op = {
            "StockTransaction": StockTransaction.objects.count(),
            "CartItem": CartItem.objects.count(),
            "OrderItem": OrderItem.objects.count(),
            "Order": Order.objects.count(),
        }
        keep = {
            "User": User.objects.count(),
            "Department": Department.objects.count(),
            "Supplier": Supplier.objects.count(),
            "Item": Item.objects.count(),
            "ManagedItem": ManagedItem.objects.count(),
        }

        if not do_delete:
            self.stdout.write("[DRY-RUN] 운영기록 초기화 예정\n")
            self.stdout.write("삭제 예정:")
            for name, n in op.items():
                self.stdout.write(f"- {name}: {n}건")
            self.stdout.write("\n유지:")
            for name, n in keep.items():
                unit = "명" if name == "User" else "개"
                self.stdout.write(f"- {name}: {n}{unit}")
            self.stdout.write(
                "\n실제 삭제하려면:\npython manage.py reset_operational_data --yes"
            )
            self._notice()
            return

        # 실제 삭제: 운영환경 가드
        if not settings.DEBUG and not options["allow_production"]:
            raise CommandError(
                "DEBUG=False(운영) 환경에서는 --allow-production 없이 실행할 수 없습니다. "
                "정말 실행하려면: --yes --allow-production"
            )

        deleted = {}
        # FK 제약 안전 순서:
        # StockTransaction.source_order_item 이 OrderItem 을 PROTECT 로 참조하므로
        # StockTransaction 을 먼저 삭제한 뒤 OrderItem/Order 를 삭제한다.
        with transaction.atomic():
            deleted["StockTransaction"] = StockTransaction.objects.all().delete()[0]
            deleted["CartItem"] = CartItem.objects.all().delete()[0]
            deleted["OrderItem"] = OrderItem.objects.all().delete()[0]
            deleted["Order"] = Order.objects.all().delete()[0]

        self.stdout.write(self.style.SUCCESS("운영기록 초기화 완료\n"))
        self.stdout.write("삭제됨:")
        for name in ("StockTransaction", "CartItem", "OrderItem", "Order"):
            self.stdout.write(f"- {name}: {deleted.get(name, 0)}건")
        self.stdout.write("\n기준정보는 유지되었습니다.")
        self.stdout.write("정식 운영 시작 전 최초재고 입력/승인을 진행하세요.")
        self._notice()

    def _notice(self):
        self.stdout.write(
            self.style.WARNING(
                "\n주의: StockTransaction 을 삭제하면 현재고 기준도 사라집니다. "
                "정식 운영 시작 전 각 관리품목별 최초재고 입력/승인이 필요합니다."
            )
        )
