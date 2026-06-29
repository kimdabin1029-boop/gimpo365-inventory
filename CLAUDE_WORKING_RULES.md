# CLAUDE_WORKING_RULES.md

# Claude Code 작업 원칙

이 문서는 김포365한의원 내부용 Django + PostgreSQL 재고관리 시스템 작업 시 반드시 지켜야 할 공통 원칙을 정리한 문서이다.

모든 작업 지시에서 별도 언급이 없더라도, 이 문서의 원칙을 우선 적용한다.

---

## 1. 프로젝트 기본 정보

이 프로젝트는 김포365한의원 내부 재고관리 시스템이다.

현재 목표는 외부 상용 서비스가 아니라, 원내에서 실제로 사용할 수 있는 단순하고 안정적인 업무 시스템을 만드는 것이다.

핵심 방향은 다음과 같다.

* 실제 운영 가능성 우선
* 단순함 우선
* 직원 교육 난이도 최소화
* 데이터 기록 보존
* 운영 중 실수 추적 가능
* 백업과 복구 가능성 확보

---

## 2. 기술 기준

반드시 PostgreSQL 기준으로 작업한다.

* SQLite 기준으로 판단하지 않는다.
* 테스트와 운영 모두 PostgreSQL 사용을 전제로 한다.
* Custom User 모델을 사용한다.
* Profile 모델은 사용하지 않는다.
* Inventory Manager 그룹은 만들지 않는다.
* 기존 역할 체계는 유지한다.

역할 계층은 다음과 같다.

```text
STAFF < TEAM_LEADER < MANAGER < ADMIN
```

---

## 3. 재고 계산 원칙

현재고는 별도 필드로 저장하지 않는다.

현재고는 항상 다음 기준으로 계산한다.

```text
APPROVED 상태의 StockTransaction.quantity_delta 합계
```

금지사항:

* 현재고 저장 필드 추가 금지
* 현재고를 직접 수정하는 기능 금지
* 거래 이력 없이 현재고만 바꾸는 기능 금지
* APPROVED 거래 합계 원칙 변경 금지

---

## 4. 거래 기록 원칙

거래 기록은 재고관리의 핵심 근거이다.

다음 원칙을 유지한다.

* 거래 삭제 금지
* 잘못 입력한 거래는 삭제가 아니라 취소 처리
* 취소 기록은 남긴다
* 과거 거래를 직접 수정하지 않는다
* 거래 상태 변경은 정해진 service 흐름을 통해 처리한다

금지사항:

* `StockTransaction.objects.create()` 직접 호출 금지
* view, form, admin, command에서 거래 `status` 직접 변경 금지
* 직접 SQL로 거래 상태 변경 금지
* 직접 SQL로 `quantity_delta` 수정 금지
* Django Admin에서 StockTransaction add/delete 권한 완화 금지

---

## 5. service 계층 원칙

StockTransaction 생성과 상태 변경은 service 계층을 우선 사용한다.

작업 중 거래 생성이나 승인/반려/취소가 필요하면 먼저 기존 service를 확인한다.

기존 service가 있다면 재사용한다.

기존 service가 없다면 다음 원칙을 따른다.

* view에서 직접 거래를 만들지 않는다.
* form에서 직접 거래를 만들지 않는다.
* admin에서 직접 거래를 만들지 않는다.
* command에서 직접 거래 상태를 바꾸지 않는다.
* 필요한 경우 service 함수를 추가한다.
* service에는 권한, 상태, 수량, 현재고 검증을 포함한다.

---

## 6. 최초재고 원칙

관리품목은 승인된 최초재고가 있어야 일반 입고/출고가 가능하다.

원칙:

* 승인된 INITIAL_COUNT가 없는 관리품목은 입고 불가
* 승인된 INITIAL_COUNT가 없는 관리품목은 출고 불가
* INITIAL_COUNT 승인대기 상태에서도 입고/출고 불가
* 최초재고 0개 승인도 유효한 최초재고로 인정
* 승인된 INITIAL_COUNT는 관리품목당 최대 1개

최초재고가 없는 품목의 실사조정 요청은 일반 ADJUSTMENT가 아니라 INITIAL_COUNT 흐름으로 처리한다.

---

## 7. 입고/출고/실사조정 기준

입고:

* 실제로 물품이 들어온 경우
* 공급업체에서 사입한 경우
* 주문 후 물품이 도착한 경우

출고:

* 실제로 물품이 사용되어 재고가 줄어든 경우
* 환자에게 지급된 경우
* 사용할 수 없는 상태가 되어 재고에서 제외해야 하는 경우

실사조정:

* 시스템 재고와 실제 재고가 맞지 않을 때
* 최초재고 등록
* 실제 재고 기준으로 수량 보정이 필요한 경우

입고/출고 입력 오류가 있으면 해당 거래를 취소하고 올바르게 재등록한다.

---

## 8. 주문 기능 원칙

주문은 입고 전 단계의 업무 기록이다.

주문은 현재고를 변경하지 않는다.

원칙:

* 주문 장바구니 추가 시 현재고 변경 없음
* 주문 확정 시 현재고 변경 없음
* 주문 취소 시 현재고 변경 없음
* 주문 입고완료 상태 변경만으로 현재고 변경 없음
* 실제 재고 증가는 기존 입고 등록으로만 발생

주문 기능과 StockTransaction을 무리하게 합치지 않는다.

Order와 OrderItem은 주문 기록용이며, StockTransaction은 실제 재고 증감 기록용이다.

---

## 9. 품목/공급업체/관리품목 원칙

거래이력이 있는 데이터는 삭제하지 않는다.

원칙:

* 품목 삭제 금지
* 관리품목 삭제 금지
* 공급업체 삭제 금지
* 더 이상 사용하지 않는 품목은 사용중지/비활성화로 관리
* 공급업체는 입고처 추적과 리포트를 위해 유지
* 동일 품목도 여러 공급업체에서 들어올 수 있음

공급업체는 등록된 Supplier 중에서 선택해야 한다.

없는 공급업체명을 자유 텍스트로 저장하면 안 된다.

---

## 10. 권한 원칙

권한 범위를 임의로 넓히지 않는다.

기본 원칙:

* STAFF는 본인 권한 범위 내 재고현황, 입고, 출고, 거래이력 중심
* TEAM_LEADER는 본인 부서 기준 실사조정/최초재고 요청 가능
* MANAGER/ADMIN은 승인/반려 및 전체 관리 가능
* 관리자용 메뉴는 STAFF에게 노출하지 않는다
* 상세 화면도 목록 화면보다 더 넓은 권한을 주면 안 된다

화면에서 숨겼더라도 view/service에서 반드시 권한을 검증한다.

---

## 11. Django Admin 원칙

Django Admin은 운영 보조 도구이지 일반 업무 화면이 아니다.

금지사항:

* StockTransaction add 허용 금지
* StockTransaction delete 허용 금지
* PROTECT 완화 금지
* 운영 편의를 이유로 Admin에서 거래를 직접 수정하게 만들지 않기

Admin 변경은 최소화한다.

---

## 12. 테스트 원칙

작업 후 반드시 관련 테스트를 실행한다.

중요 작업 후에는 전체 테스트를 실행한다.

기본 확인:

```powershell
python manage.py check
python manage.py test
```

또는 프로젝트에서 사용하는 PostgreSQL 테스트 명령을 따른다.

테스트 대상:

* 권한
* 거래 생성
* 거래 취소
* 최초재고 차단
* 현재고 계산
* 주문 기능은 현재고 비변경
* management command dry-run
* 화면 접근 권한

---

## 13. management command 원칙

운영 데이터에 영향을 줄 수 있는 command는 반드시 안전장치를 둔다.

원칙:

* 기본 실행은 dry-run
* 실제 실행은 `--yes` 필요
* 삭제/초기화 대상 건수 출력
* DEBUG=False 환경에서는 위험 command 실행 차단
* 운영 화면에 위험 기능 버튼을 만들지 않는다
* 실행 전 백업을 권장한다

알파/교육용 command는 실제 운영 중 사용하지 않는다.

---

## 14. 백업 원칙

운영 데이터 변경 전에는 백업을 우선한다.

특히 다음 작업 전에는 반드시 백업한다.

* 거래기록 초기화
* 마이그레이션 적용
* 대량 데이터 수정
* 운영 DB에 영향을 주는 command 실행
* 수동 복구 작업

백업 후 확인할 것:

* dump 파일 생성
* 파일 크기 0 아님
* OneDrive 동기화 확인
* 필요 시 `pg_restore -l` 검증

---

## 15. 문서화 원칙

운영 기준이 바뀌면 문서를 함께 수정한다.

주요 문서:

* README.md
* PRODUCT_SPEC.md
* TECH_SPEC.md
* OPERATIONS_SETUP.md
* DB_OPERATIONS.md
* TASKS.md
* NEXT_ROADMAP.md
* 직원용 사용법 문서
* 관리자용 운영 문서

새 기능을 만들 때는 최소한 다음을 문서화한다.

* 목적
* 사용 대상
* 업무 절차
* 예외 상황
* 권한
* 운영상 주의점

---

## 16. 개발 범위 원칙

작업 지시 범위를 벗어나지 않는다.

금지사항:

* 요청하지 않은 대규모 리팩터링 금지
* 요청하지 않은 모델 변경 금지
* 요청하지 않은 마이그레이션 금지
* 요청하지 않은 UI 전면 개편 금지
* 요청하지 않은 새 앱 생성 금지
* 다중 지점/MSO 구조를 임의로 추가하지 않기
* HR, Notice, SOP 등 새 모듈을 임의로 구현하지 않기

큰 구조 변경이 필요하면 먼저 이유와 대안을 보고한다.

---

## 17. 커밋 원칙

작업 단위는 작게 유지한다.

커밋 전 확인:

```powershell
git status
python manage.py check
python manage.py test
```

커밋 메시지는 작업 성격이 드러나게 작성한다.

예:

```text
HOTFIX block stock transactions before initial count approval
HOTFIX improve alpha usability navigation dashboard and approval queue
FEAT add order cart and order tracking MVP
DOCS add next roadmap for inventory and OS direction
```

---

## 18. 운영 철학

이 시스템은 직원의 실수를 처벌하기 위한 도구가 아니다.

목적은 다음과 같다.

* 입력 실수 방지
* 업무 기준 통일
* 재고 흐름 추적
* 인수인계 가능성 확보
* 운영 누락 감소
* 관리자 확인 부담 감소

직원 교육으로 막기 어려운 실수는 시스템에서 차단한다.

하지만 시스템이 너무 복잡해져서 직원이 쓰기 어려워지면 안 된다.
