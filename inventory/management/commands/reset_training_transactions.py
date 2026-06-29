"""알파/교육용 거래기록 초기화 (DEBUG 전용).

목적:
- 알파테스트 또는 직원 교육 중 입력된 StockTransaction 만 정리한다.
- 공급업체(Supplier) / 품목(Item) / 관리품목(ManagedItem) / 부서(Department) / 사용자(User)는
  모두 그대로 유지한다. (reset_alpha_data 와 달리 마스터/조직 데이터는 건드리지 않는다.)

주의:
- 이 명령은 "운영 데이터 정정" 기능이 아니다. 실제 운영 중에는 사용하지 않는다.
- 운영(DEBUG=False) 환경에서는 무조건 실행을 거부한다.
- 기본 동작은 dry-run(미삭제)이며, --yes 옵션이 있을 때만 실제 삭제한다.
- 거래 status 를 직접 변경하거나 StockTransaction 을 새로 생성하지 않는다. (삭제만 수행)
- 기간 필터는 거래일자(occurred_at) 기준이다.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count
from django.utils.dateparse import parse_date

from inventory.models import (
    OUT_TRANSACTION_TYPES,
    StockTransaction,
    TransactionStatus,
    TransactionType,
)

# 거래유형 요약 버킷 (OUT 계열은 하나로 묶어 표시)
_TYPE_BUCKET_ORDER = ["INITIAL_COUNT", "IN", "OUT", "ADJUSTMENT"]
# 상태 요약 표시 순서
_STATUS_ORDER = [
    TransactionStatus.PENDING,
    TransactionStatus.APPROVED,
    TransactionStatus.REJECTED,
    TransactionStatus.CANCELED,
]


def _type_bucket(transaction_type: str) -> str:
    """거래유형을 요약 버킷명으로 변환. OUT 계열은 'OUT' 로 묶는다."""
    if transaction_type in OUT_TRANSACTION_TYPES:
        return "OUT"
    if transaction_type == TransactionType.IN:
        return "IN"
    if transaction_type == TransactionType.INITIAL_COUNT:
        return "INITIAL_COUNT"
    if transaction_type == TransactionType.ADJUSTMENT:
        return "ADJUSTMENT"
    return transaction_type  # 기타(미래 신규 유형 대비)


class Command(BaseCommand):
    help = (
        "알파/교육용 거래기록(StockTransaction) 초기화 (DEBUG 전용). "
        "기본은 dry-run 이며 --yes 일 때만 실제 삭제. "
        "공급업체/품목/관리품목/부서/사용자는 유지. 운영 환경에서는 실행되지 않는다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help="실제 삭제 수행. (미지정 시 dry-run 으로 동작)",
        )
        parser.add_argument(
            "--from",
            dest="date_from",
            metavar="YYYY-MM-DD",
            help="삭제 대상 시작 거래일자(occurred_at, 포함).",
        )
        parser.add_argument(
            "--to",
            dest="date_to",
            metavar="YYYY-MM-DD",
            help="삭제 대상 종료 거래일자(occurred_at, 포함).",
        )

    def _parse_date(self, value, label):
        if not value:
            return None
        parsed = parse_date(value)
        if parsed is None:
            raise CommandError(f"{label} 날짜 형식이 올바르지 않습니다 (YYYY-MM-DD): {value}")
        return parsed

    def handle(self, *args, **options):
        # 가드: 운영(DEBUG=False)에서는 무조건 중단
        if not settings.DEBUG:
            raise CommandError(
                "DEBUG=False 환경에서는 실행할 수 없습니다. "
                "(운영 데이터 보호 — 알파/교육용 명령)"
            )

        date_from = self._parse_date(options.get("date_from"), "--from")
        date_to = self._parse_date(options.get("date_to"), "--to")

        qs = StockTransaction.objects.all()
        if date_from:
            qs = qs.filter(occurred_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(occurred_at__date__lte=date_to)

        total = qs.count()

        # 거래유형별 집계 (OUT 계열 묶음 + 기타)
        type_counts = {}
        for row in qs.values("transaction_type").annotate(c=Count("id")):
            bucket = _type_bucket(row["transaction_type"])
            type_counts[bucket] = type_counts.get(bucket, 0) + row["c"]

        # 상태별 집계
        status_counts = {
            row["status"]: row["c"]
            for row in qs.values("status").annotate(c=Count("id"))
        }

        # 출력: 기간
        period = (
            f"{date_from or '처음'} ~ {date_to or '마지막'}"
            if (date_from or date_to)
            else "전체 기간"
        )
        self.stdout.write(f"삭제 대상 거래기록 (거래일자 기준: {period})")
        self.stdout.write(f"  총 {total} 건")

        # 출력: 거래유형별 (표준 버킷 → 기타 순서)
        self.stdout.write("거래유형별:")
        shown = set()
        for name in _TYPE_BUCKET_ORDER:
            self.stdout.write(f"  - {name}: {type_counts.get(name, 0)}")
            shown.add(name)
        for name, c in sorted(type_counts.items()):
            if name not in shown:
                self.stdout.write(f"  - {name}(기타): {c}")

        # 출력: 상태별 (표준 4종 → 기타 순서)
        self.stdout.write("상태별:")
        shown_status = set()
        for status in _STATUS_ORDER:
            self.stdout.write(f"  - {status}: {status_counts.get(status, 0)}")
            shown_status.add(status)
        for status, c in sorted(status_counts.items()):
            if status not in shown_status:
                self.stdout.write(f"  - {status}(기타): {c}")

        self.stdout.write(
            "유지: 공급업체 / 품목 / 관리품목 / 부서 / 사용자 (StockTransaction 만 삭제)"
        )

        # dry-run (기본): 실제 삭제 없음
        if not options["yes"]:
            self.stdout.write(
                self.style.WARNING(
                    "[dry-run] 실제 삭제를 수행하지 않았습니다. "
                    "실제 삭제하려면 --yes 를 지정하세요."
                )
            )
            return

        with transaction.atomic():
            deleted = qs.delete()[0]

        self.stdout.write(self.style.SUCCESS(f"삭제 완료: StockTransaction {deleted} 건"))
