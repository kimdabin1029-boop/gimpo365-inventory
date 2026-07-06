"""정식 운영 전 기준정보 점검 (읽기 전용). (v0.2.5)

관리자 웹 화면(기준정보 점검)/기준정보 엑셀과 동일한 로직(master_data_checks)을 사용한다.
데이터를 변경하지 않는다.
"""

from django.core.management.base import BaseCommand

from inventory.master_data_checks import CHECK, WARNING, run_master_data_checks


class Command(BaseCommand):
    help = "정식 운영 전 기준정보 누락/오류 점검 (읽기 전용, 변경 없음)."

    def handle(self, *args, **options):
        r = run_master_data_checks()

        self.stdout.write("[기준정보 점검 결과]\n")
        self.stdout.write("요약:")
        self.stdout.write(f"- 점검 대상 활성 관리품목: {r['active_count']}개")
        self.stdout.write(f"- 경고 항목: {r['warning_count']}건")
        self.stdout.write(f"- 확인 필요 항목: {r['check_count']}건")
        self.stdout.write(f"- 기준정보 정상 항목: {r['normal_count']}개")

        self.stdout.write("\n경고:")
        warn = [s for s in r["sections"] if s["severity"] == WARNING]
        for i, s in enumerate(warn, 1):
            self.stdout.write(f"{i}. {s['title']}: {s['count']}개")

        self.stdout.write("\n운영 시작 전 확인:")
        for s in r["sections"]:
            if s["severity"] == CHECK:
                self.stdout.write(f"- {s['title']}: {s['count']}개")

        self.stdout.write(
            "\n상세 내역은 관리자 > 기준정보 점검 화면에서 확인하세요."
        )
        self.stdout.write(
            "참고: 운영기록 초기화 직후에는 모든 관리품목이 '최초재고 미입력'으로 "
            "표시되는 것이 정상입니다."
        )
