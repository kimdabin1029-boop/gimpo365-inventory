# gimpo365-inventory v0.1 PRODUCT_SPEC

## 0. 문서 목적

이 문서는 `gimpo365-inventory` v0.1 개발 전, 프로젝트의 목적·범위·사용자·권한·데이터 구조·상태 전이·운영 기준을 확정하기 위한 제품 명세서다.

이 문서는 개발 구현 명세가 아니라, 기술명세 작성 전 제품·운영 기준을 확정하기 위한 상위 명세다.

후속 문서 구조는 다음과 같다.

```text
PRODUCT_SPEC.md  ← 현재 문서
TECH_SPEC.md     ← 개발 구현 명세
TASKS.md         ← Codex / Claude Code 작업 지시서
```

이 문서는 기존 본문과 이후 보완사항을 병합한 단일 확정본이다.  
후속 작업에서는 이 문서만 기준으로 삼고, 이전 초안이나 분리된 보완문서는 참조하지 않는다.

---

# 1. 프로젝트 개요

## 1.1 프로젝트명

```text
gimpo365-inventory
```

## 1.2 프로젝트 성격

`gimpo365-inventory`는 김포365OS 전체가 아니라, 김포365OS의 첫 번째 독립 모듈이다.

v0.1은 재고관리만을 대상으로 한다.

이 프로젝트는 기존 AppSheet 또는 Google Sheets 기반 재고관리 구조를 참고하되, 이를 그대로 이전하거나 보강하는 프로젝트가 아니다.

7월 기준으로 재고관리 방식을 하드리셋하고, Django + PostgreSQL 기반의 새 재고관리 시스템에서 새 기준으로 운영을 시작하는 것을 목표로 한다.

## 1.3 프로젝트 목적

`gimpo365-inventory`는 김포365한의원 내부에서 사용하는 소모품, 의료용품, 미용소모품, 위생용품, 의약품, 일반소모품 등의 재고를 표준화된 방식으로 관리하기 위한 내부 재고관리 시스템이다.

이 시스템의 목적은 단순히 현재 수량을 기록하는 것이 아니다.

매출 중심의 결과지표만으로는 알 수 없는 실제 운영지표를 구조화하여, 병원 운영의 완성도를 높이는 것을 목표로 한다.

관리하고자 하는 운영지표는 다음과 같다.

```text
입고량
사용량
폐기량
분실량
증정/기타출고량
실사조정 내역
최소재고 이하 품목
보관장소
공급업체
입력자
부서별 사용 흐름
```

## 1.4 핵심 문제의식

현재 중소규모 병·의원 운영에서 재고관리는 특정 팀장 또는 일부 숙련자의 기억, 감각, 책임감에 의존하기 쉽다.

이 방식은 단기적으로 편리해 보일 수 있으나, 다음과 같은 문제가 있다.

```text
담당자가 휴무이거나 퇴사하면 업무가 끊긴다.
발주 기준이 감각에 의존한다.
재고 부족이 사전에 보이지 않는다.
실제 사용량과 매출의 관계를 분석하기 어렵다.
폐기와 사용이 구분되지 않는다.
특정 개인이 정보를 독점하는 구조가 생긴다.
후임자나 신규 직원이 재고관리 방식을 배우기 어렵다.
```

따라서 재고관리는 특정 개인의 노하우가 아니라, 파트 전체가 공유하는 표준 업무로 전환되어야 한다.

## 1.5 운영 철학

매출은 결과지표다.

그러나 사업체의 완성도를 보려면 매출뿐 아니라 실제 현장에서 무엇이 얼마나 소비되고 있는지에 대한 소비지표가 필요하다.

`gimpo365-inventory`는 실무자가 정확하게 입력한 소비지표를 기반으로 운영진이 더 정확한 판단을 할 수 있게 만드는 시스템이다.

핵심 문장:

```text
매출은 성과를 보여주지만, 소비지표는 운영의 질을 보여준다.
```

---

# 2. v0.1 범위

## 2.1 v0.1의 목표

v0.1의 목표는 병원 전체 운영시스템을 만드는 것이 아니다.

v0.1은 재고관리만을 대상으로 한다.

정확한 목표는 다음과 같다.

```text
7월 기준으로 기존 AppSheet / Google Sheets 재고관리 흐름을 하드리셋하고,
Django + PostgreSQL 기반의 새 재고관리 시스템에서
피부실(스킨앤라인) 또는 치료실 중 최소 1개 파트가
입고, 사용, 폐기, 실사조정 요청, 현재고 조회를 실제로 수행할 수 있게 한다.
```

## 2.2 포함 기능

v0.1에 포함하는 기능은 다음과 같다.

```text
직원 로그인
부서 관리
역할/권한 관리
품목 마스터 관리
부서별 관리품목 관리
공급업체 관리
초기재고 입력
초기재고 승인/반려
초기재고 일괄 승인
입고 등록
출고 등록
폐기 등록
분실 등록
증정/기타출고 등록
실사조정 요청
실사조정 승인/반려
PENDING 거래 철회
APPROVED 거래 취소
현재고 조회
최소재고 이하 품목 조회
거래 이력 조회
Django Admin 기반 관리자 관리
```

## 2.3 제외 기능

v0.1에서는 다음 기능을 제외한다.

```text
탕전 큐 관리
처방전 작성
차트프로그램 연동
환자 정보 관리
문진 기록
컴플레인 관리
자동 발주
카카오톡/문자 알림
시술별 원가 자동 계산
고급 통계 대시보드
비품/장비 자산관리 고도화
기존 AppSheet 데이터 마이그레이션
PIN 로그인
입력 누락 여부 판단
박스-낱개 단위 자동 변환
유통기한 임박 알림
재고금액/FIFO/LIFO 평가
커스텀 마스터 관리 화면
커스텀 사용자 관리 화면
```

---

# 3. 조직 및 부서 정의

## 3.1 스킨앤라인의 위치

v0.1에서 스킨앤라인은 별도 법인, 별도 사업장, 별도 테넌트로 취급하지 않는다.

스킨앤라인은 김포365한의원 내부의 피부실 브랜드 또는 피부실 파트로 본다.

따라서 v0.1에서는 멀티테넌시, 조직별 데이터 격리, 법인별 권한 분리는 구현하지 않는다.

## 3.2 기본 부서

v0.1에서 사용할 수 있는 부서 예시는 다음과 같다.

```text
피부실(스킨앤라인)
치료실
데스크
진료부
탕전실
```

다만 v0.1의 실제 적용 대상은 다음 중 1개 또는 2개 부서로 제한한다.

```text
피부실(스킨앤라인)
치료실
```

탕전실은 v0.1 재고관리 실사용 대상에서 제외한다.

탕전실 재고는 약재, 처방, 조제, 탕전 큐와 연결될 가능성이 높으므로 별도 단계에서 검토한다.

## 3.3 운영진의 정의

운영진은 부서가 아니라 역할로 관리한다.

즉, `운영진`이라는 Department를 권한 판단의 기준으로 사용하지 않는다.

운영진 권한은 `MANAGER` 역할로 표현한다.

---

# 4. 사용자 역할과 권한 구조

> **v0.1.1 운영 정책 변경 (알파테스트 반영, 이 절의 일부 초기 서술보다 우선)**
>
> - **실사조정 요청과 최초 재고 입력(INITIAL_COUNT)은 TEAM_LEADER 이상**만 생성할 수 있다.
>   STAFF 는 실사조정 요청/최초 재고 입력을 생성할 수 없다(메뉴 미노출, URL 접근 403).
> - 사용자 화면의 별도 '초기재고 입력'은 **'실사조정 요청' 화면으로 통합**되었다.
>   선택 품목에 승인된 최초 재고가 없으면 INITIAL_COUNT(최초 재고 입력), 있으면 ADJUSTMENT(실사조정)로
>   자동 분기한다. 내부 거래유형/유일성/현재고 계산/승인 전 미반영 원칙은 그대로 유지된다.
> - 직접 거래 취소 가능 여부는 거래일자가 아니라 **입력일시(created_at) 기준 당일**이다.
> - 따라서 §4.3 의 "STAFF … 실사조정 요청 / 초기재고 입력 요청" 서술은 v0.1.1 에서
>   "TEAM_LEADER 이상"으로 대체된다. (승인/반려는 기존대로 MANAGER 이상)

## 4.1 역할 목록

v0.1의 역할은 다음 네 가지로 단순화한다.

```text
STAFF
TEAM_LEADER
MANAGER
ADMIN
```

`Doctor`는 v0.1의 기본 역할에서 제외한다.

진료원장이 재고 시스템을 사용해야 할 경우, 별도 `Doctor` 역할을 만들지 않고 필요 권한에 따라 `STAFF`, `TEAM_LEADER`, `MANAGER` 중 하나를 부여한다.

예:

```text
진료원장이 특정 부서 재고만 입력/조회하면 됨 → STAFF
진료원장이 특정 부서 전체 재고 흐름을 봐야 함 → TEAM_LEADER
진료원장이 전체 재고를 봐야 함 → MANAGER
```

v0.1에서는 권한 구조를 단순하게 유지한다.

## 4.2 권한 상속 구조

v0.1의 권한은 계층형으로 설계한다.

```text
STAFF < TEAM_LEADER < MANAGER < ADMIN
```

상위 역할은 하위 역할의 기능을 모두 포함한다.

즉, `ADMIN`은 시스템 관리만 하는 계정이 아니라, `STAFF`, `TEAM_LEADER`, `MANAGER` 기능을 모두 수행할 수 있다.

마찬가지로 `MANAGER`는 입고 등록, 출고 등록, 현재고 조회 등 일반 직원 기능을 모두 수행할 수 있다.

## 4.3 STAFF

기본 직원 권한.

가능한 기능:

```text
본인 부서 관리품목 조회
본인 부서 입고 등록
본인 부서 출고 등록
본인 부서 현재고 조회
본인 부서 최소재고 이하 품목 조회
본인 부서 거래 이력 읽기 전용 조회
본인 부서 관리품목에 대한 실사조정 요청
본인 부서 관리품목에 대한 초기재고 입력 요청
본인이 생성한 PENDING 거래 철회
본인이 당일 등록한 APPROVED 일반 거래 취소
```

제한:

```text
타 부서 품목 조회 불가
타 부서 거래 조회 불가
다른 사용자가 입력한 거래 취소 불가
실사조정 승인 불가
초기재고 승인 불가
품목 마스터 수정 불가
부서별 관리품목 수정 불가
공급업체 수정 불가
사용자 관리 불가
Django Admin 접근 불가
```

STAFF도 실사조정 요청은 가능하다.

이유는 시스템 재고와 실제 재고가 어긋난 상황에서 STAFF가 아무 기록도 남기지 못하는 운영 데드락을 방지하기 위함이다.

단, STAFF가 생성한 실사조정 요청과 초기재고 입력은 항상 `PENDING` 상태이며, MANAGER 이상이 승인해야 현재고에 반영된다.

## 4.4 TEAM_LEADER

`TEAM_LEADER`는 `STAFF` 권한을 모두 포함한다.

추가 가능한 기능:

```text
본인 부서 전체 거래 기록 조회
본인 부서 전체 직원 입력 기록 조회
본인 부서 실사조정 요청
본인 부서 초기재고 입력 요청
본인 부서 최소재고 이하 품목 확인
본인 부서 재고 흐름 확인
본인 부서 당일 APPROVED 일반 거래 취소
```

제한:

```text
타 부서 품목 및 거래 기록 조회 불가
실사조정 승인 불가
초기재고 승인 불가
사용자 관리 불가
시스템 설정 불가
Django Admin 접근 불가
```

## 4.5 MANAGER

`MANAGER`는 `TEAM_LEADER` 권한을 모두 포함한다.

추가 가능한 기능:

```text
전체 부서 관리품목 조회
전체 부서 입고 등록
전체 부서 출고 등록
전체 부서 거래 기록 조회
전체 부서 현재고 조회
전체 부서 최소재고 이하 품목 조회
전체 부서 실사조정 요청
전체 부서 초기재고 입력
실사조정 승인/반려
초기재고 승인/반려
초기재고 일괄 승인
APPROVED 거래 취소
```

`MANAGER`는 운영진 계정으로, 특정 부서에 소속되어 있더라도 전체 부서 재고를 조회하고 관리할 수 있다.

v0.1에서는 MANAGER 사용자 기본 관리 커스텀 기능을 구현하지 않는다.

사용자 생성, 비활성화, 비밀번호 초기화, 역할 변경은 Django Admin에서 처리한다.

## 4.6 ADMIN

`ADMIN`은 `MANAGER` 권한을 모두 포함한다.

추가 가능한 기능:

```text
전체 사용자 계정 관리
모든 역할 변경
MANAGER 권한 부여
ADMIN 권한 부여
부서 생성/수정/비활성화
시스템 설정 관리
예외 데이터 수정
Django Admin 전체 접근
데이터 삭제 또는 복구 처리
```

`ADMIN`은 시스템 최고 관리자 권한이다.

`ADMIN`도 일반 운영 화면에서 입고 등록, 출고 등록, 현재고 조회, 실사조정 승인 등을 모두 수행할 수 있어야 한다.

## 4.7 권한 적용 원칙

```text
상위 역할은 하위 역할 기능을 모두 포함한다.
STAFF와 TEAM_LEADER는 본인 부서 범위 안에서만 작업한다.
MANAGER와 ADMIN은 부서 제한 없이 전체 데이터를 조회하고 입력할 수 있다.
Django Admin 접근은 ADMIN을 기본으로 하며, 필요 시 MANAGER 일부에게 제한적으로 부여할 수 있다.
일반 운영 화면과 Django Admin 권한은 구분한다.
역할 변경과 관리자 권한 부여는 ADMIN 전용 기능이다.
MANAGER의 사용자 기본 관리 커스텀 기능은 v0.2 이후 검토한다.
```

---

# 5. 데이터 구조 핵심 결정

## 5.1 품목과 부서 관계

품목과 부서의 관계는 단순 1:N으로 처리하지 않는다.

현실적으로 같은 품목을 여러 부서가 사용할 수 있고, 같은 품목이라도 부서마다 최소재고, 보관장소, 공급업체가 다를 수 있기 때문이다.

따라서 v0.1에서는 다음 구조를 사용한다.

```text
Item
- 전역 품목 마스터

ManagedItem
- 특정 부서가 관리하는 품목
- Item + Department 조합
```

재고 거래는 `Item`이 아니라 `ManagedItem`에 연결한다.

## 5.2 재고 원장 구조

v0.1에서는 `StockIn`, `StockOut`, `StockAdjustment`를 별도 테이블로 나누지 않는다.

대신 `StockTransaction` 단일 원장으로 관리한다.

이유:

```text
입고, 출고, 폐기, 분실, 실사조정, 초기재고를 하나의 거래 이력으로 일관되게 관리할 수 있다.
현재고 계산 기준이 단순해진다.
거래 이력이 한 곳에 모인다.
```

거래 유형은 다음과 같다.

```text
INITIAL_COUNT
IN
OUT_USE
OUT_DISCARD
OUT_LOST
OUT_GIFT
OUT_OTHER
ADJUSTMENT
```

모든 거래는 `quantity_delta`를 가진다.

예:

```text
입고 10개       → quantity_delta = +10
사용 2개       → quantity_delta = -2
폐기 1개       → quantity_delta = -1
분실 1개       → quantity_delta = -1
증정 1개       → quantity_delta = -1
기타출고 1개   → quantity_delta = -1
초기실사 20개  → quantity_delta = +20
실사조정 -2개  → quantity_delta = -2
```

## 5.3 현재고 계산 방식

현재고는 별도 필드로 직접 저장하지 않는다.

현재고는 승인된 거래의 `quantity_delta` 합계로 계산한다.

```text
현재고 = APPROVED 상태의 StockTransaction.quantity_delta 합계
```

현재고 계산에 포함되는 거래:

```text
APPROVED 상태의 거래
```

현재고 계산에서 제외되는 거래:

```text
PENDING
REJECTED
CANCELED
```

## 5.4 실사조정 방식

실사조정은 절대값 입력 방식으로 받되, 시스템에는 delta로 저장한다.

실사조정 요청 시 시스템은 현재 계산 재고를 `expected_quantity`로 저장하고, 사용자가 입력한 실제 재고를 `actual_quantity`로 저장한다.

계산 방식:

```text
difference = actual_quantity - expected_quantity
quantity_delta = difference
```

예:

```text
시스템 현재고: 7
실제 실사수량: 5
difference: -2
quantity_delta: -2
```

실사조정은 승인 전에는 현재고에 반영하지 않는다.

## 5.5 초기재고 방식

초기재고는 `INITIAL_COUNT` 거래로 저장한다.

초기재고는 해당 `ManagedItem`의 기준 재고를 처음 설정하는 거래다.

기존 AppSheet 또는 Google Sheets 데이터는 마이그레이션하지 않으며, 7월 기준 실사 결과를 새 시스템에 입력한다.

초기재고는 승인 전에는 현재고에 반영하지 않는다.

상태 규칙:

```text
STAFF가 생성한 INITIAL_COUNT → PENDING
TEAM_LEADER가 생성한 INITIAL_COUNT → PENDING
MANAGER가 생성한 INITIAL_COUNT → APPROVED
ADMIN이 생성한 INITIAL_COUNT → APPROVED
```

## 5.6 INITIAL_COUNT 유일성

하나의 `ManagedItem`에는 `APPROVED` 상태의 `INITIAL_COUNT`가 최대 1건만 존재할 수 있다.

이 제약은 생성 시점뿐 아니라 승인 시점에도 반드시 검사한다.

### 생성 시점 규칙

새 `INITIAL_COUNT`를 생성하려 할 때 다음 조건을 확인한다.

```text
같은 ManagedItem에 APPROVED INITIAL_COUNT가 이미 있음 → 생성 차단
같은 ManagedItem에 PENDING INITIAL_COUNT가 이미 있음 → 경고 표시
```

`PENDING INITIAL_COUNT`가 이미 있는 경우에도 운영상 필요하면 추가 생성은 가능하다.

단, 승인 시점에서 최종 유일성 검사를 다시 수행한다.

### 승인 시점 규칙

`INITIAL_COUNT`를 승인하려 할 때 다음 조건을 반드시 확인한다.

```text
승인하려는 ManagedItem에 APPROVED INITIAL_COUNT가 이미 있으면 승인 차단
```

일괄 승인에서도 동일하게 적용한다.

### 일괄 승인 규칙

`INITIAL_COUNT` 일괄 승인 시, 각 거래별로 승인 가능 여부를 개별 검사한다.

```text
APPROVED INITIAL_COUNT가 이미 없는 ManagedItem → 승인 가능
APPROVED INITIAL_COUNT가 이미 있는 ManagedItem → 승인 스킵 또는 차단
```

일괄 승인 결과는 사용자에게 표시한다.

예:

```text
승인 완료: 18건
승인 제외: 2건
제외 사유: 이미 승인된 초기재고가 있음
```

초기재고가 이미 승인된 품목의 재고 차이는 새 `INITIAL_COUNT`를 추가하지 않고 `ADJUSTMENT`로 처리한다.

## 5.7 거래 상태

`StockTransaction`은 상태값을 가진다.

```text
PENDING
APPROVED
REJECTED
CANCELED
```

상태 적용 원칙:

```text
일반 입고: 생성 즉시 APPROVED
일반 사용/폐기/분실/증정/기타출고: 생성 즉시 APPROVED
MANAGER 또는 ADMIN이 생성한 초기재고: 생성 즉시 APPROVED
STAFF 또는 TEAM_LEADER가 생성한 초기재고: 생성 시 PENDING
실사조정: 생성 시 PENDING
실사조정 승인 시 APPROVED
초기재고 승인 시 APPROVED
실사조정 반려 시 REJECTED
초기재고 반려 시 REJECTED
철회 또는 취소 시 CANCELED
```

## 5.8 거래 상태 전이

v0.1의 StockTransaction 상태 전이는 다음을 따른다.

```text
PENDING → APPROVED
PENDING → REJECTED
PENDING → CANCELED

APPROVED → CANCELED

REJECTED → 변경 불가
CANCELED → 변경 불가
```

### PENDING → APPROVED

승인 권한자:

```text
MANAGER
ADMIN
```

승인 시 현재고 계산에 반영된다.

### PENDING → REJECTED

반려 권한자:

```text
MANAGER
ADMIN
```

반려 시 현재고 계산에 반영되지 않는다.

### PENDING → CANCELED

철회 권한자:

```text
거래 생성자
MANAGER
ADMIN
```

철회 시 현재고 계산에 반영되지 않는다.

### APPROVED → CANCELED

오입력 정정을 위한 취소 처리다.

거래를 물리적으로 삭제하거나 직접 수정하지 않는다.

취소 시 현재고 계산에서 제외된다.

단, 취소 후 현재고가 0 미만이 되는 경우 일반 운영 화면에서는 취소할 수 없다.

## 5.9 부족 품목 판단 기준

부족 또는 발주 후보 기준은 다음으로 통일한다.

```text
현재고 <= 최소재고
```

명칭은 가능하면 “부족 품목”보다 다음 용어를 우선 사용한다.

```text
최소재고 이하 품목
발주 후보 품목
```

현재고가 최소재고와 같은 경우도 발주 후보로 본다.

## 5.10 현재고 초과 출고

일반 운영 화면에서는 현재고를 초과하는 출고를 허용하지 않는다.

현재고가 실제와 다를 경우, 출고를 강제로 등록하지 않고 실사조정 요청을 먼저 진행한다.

## 5.11 현재고 음수 방지

v0.1에서는 현재고 음수를 허용하지 않는다.

일반 운영 화면에서는 거래 등록 또는 거래 취소 결과 현재고가 0 미만이 되는 작업을 차단한다.

```text
출고 후 현재고 < 0 이면 저장 불가
취소 후 현재고 < 0 이면 취소 불가
```

---

# 6. 오입력 정정 및 거래 취소

## 6.1 오입력 정정 원칙

v0.1에서는 이미 저장된 거래를 직접 수정하지 않는다.

잘못 입력한 거래는 삭제하거나 수정하지 않고, `CANCELED` 상태로 변경한다.

정정이 필요한 경우 다음 절차를 따른다.

```text
1. 잘못 입력한 거래를 CANCELED 처리한다.
2. 올바른 거래를 새로 입력한다.
```

거래를 실제 삭제하지 않는다.

## 6.2 PENDING 거래 철회

v0.1에서는 PENDING 상태의 거래를 생성자가 승인 전 철회할 수 있다.

철회는 거래를 삭제하는 것이 아니라 `CANCELED` 상태로 변경하는 것이다.

대상 거래:

```text
INITIAL_COUNT
ADJUSTMENT
```

철회 가능 조건:

```text
status = PENDING
created_by = 현재 사용자
아직 승인 또는 반려되지 않음
```

철회 결과:

```text
status = CANCELED
canceled_by = 현재 사용자
canceled_at = 현재 시각
cancel_reason = 사용자 입력 사유
```

## 6.3 APPROVED 거래 취소 권한

거래 취소는 역할에 따라 다음과 같이 허용한다.

### STAFF

STAFF는 본인이 당일 등록한 APPROVED 일반 거래를 취소할 수 있다.

조건:

```text
created_by = 현재 사용자
created_at = 오늘
status = APPROVED
transaction_type이 INITIAL_COUNT 또는 ADJUSTMENT가 아님
취소 후 현재고가 0 미만이 되지 않음
```

취소 가능 거래:

```text
IN
OUT_USE
OUT_DISCARD
OUT_LOST
OUT_GIFT
OUT_OTHER
```

STAFF는 다른 사용자가 입력한 거래를 취소할 수 없다.

STAFF는 INITIAL_COUNT 또는 ADJUSTMENT 거래를 취소할 수 없다.

### TEAM_LEADER

TEAM_LEADER는 STAFF 권한을 포함한다.

추가로 본인 부서의 당일 APPROVED 일반 거래를 취소할 수 있다.

조건:

```text
거래의 ManagedItem.department = 본인 부서
created_at = 오늘
status = APPROVED
transaction_type이 INITIAL_COUNT 또는 ADJUSTMENT가 아님
취소 후 현재고가 0 미만이 되지 않음
```

### MANAGER

MANAGER는 전체 부서 APPROVED 거래를 취소할 수 있다.

조건:

```text
status = APPROVED
취소 사유 입력 필수
취소 후 현재고가 0 미만이 되지 않음
```

MANAGER는 운영진 판단으로 거래를 취소할 수 있으나, 모든 취소 이력은 남겨야 한다.

### ADMIN

ADMIN은 MANAGER 권한을 포함한다.

ADMIN은 예외 상황에서 전체 거래를 취소할 수 있다.

단, ADMIN도 거래를 물리적으로 삭제하지 않는다.

## 6.4 취소 시 기록해야 하는 정보

`StockTransaction`에는 취소 관련 필드를 둔다.

```text
canceled_by
canceled_at
cancel_reason
```

필드 설명:

```text
canceled_by: 거래를 취소한 사용자
canceled_at: 거래가 취소된 시각
cancel_reason: 취소 사유
```

거래가 `CANCELED` 상태가 되면 현재고 계산에서 제외한다.

## 6.5 거래 취소의 당일 기준

STAFF와 TEAM_LEADER의 거래 취소 권한은 당일 거래로 제한한다.

당일 기준은 `created_at`의 날짜를 기준으로 한다.

다음 날 발견된 오입력은 MANAGER 또는 ADMIN이 처리한다.

이 기준은 v0.1에서 운영 단순성과 추적성을 우선하기 위한 결정이다.

---

# 7. 데이터 모델 초안

## 7.1 Department

부서 정보.

필드:

```text
id
name
is_active
active_for_inventory
memo
created_at
updated_at
```

설명:

```text
active_for_inventory = False인 부서는 v0.1 재고관리 대상에서 제외된다.
```

## 7.2 User

직원 계정.

Django 기본 User 모델을 확장하거나 Profile 모델을 둔다.

필드:

```text
id
username
name
department
role
is_active
last_login
created_at
updated_at
```

역할:

```text
STAFF
TEAM_LEADER
MANAGER
ADMIN
```

## 7.3 Supplier

공급업체 정보.

필드:

```text
id
name
phone
homepage
manager_name
manager_phone
memo
is_active
created_at
updated_at
```

## 7.4 Item

전역 품목 마스터.

필드:

```text
id
name
category
specification
memo
is_active
created_at
updated_at
```

분류:

```text
미용소모품
의료용품
위생용품
의약품
일반소모품
전용소모품
기타
```

## 7.5 ManagedItem

부서별 관리품목.

필드:

```text
id
item
department
unit
minimum_stock
storage_location
default_supplier
is_active
memo
created_at
updated_at
```

설명:

```text
ManagedItem은 Item + Department 조합이다.
재고 거래는 ManagedItem 기준으로 발생한다.
default_supplier는 해당 부서 관리품목의 기본 공급업체다.
```

제약:

```text
같은 department 안에서 같은 item은 중복 등록하지 않는다.
운영 개시 후 unit 변경 금지.
```

## 7.6 StockTransaction

재고 거래 원장.

필드:

```text
id
managed_item
transaction_type
status
quantity_delta
quantity_input
expected_quantity
actual_quantity
occurred_at
created_by
approved_by
approved_at
supplier
unit_price
expiration_date
memo
canceled_by
canceled_at
cancel_reason
created_at
updated_at
```

### transaction_type

거래 유형.

```text
INITIAL_COUNT
IN
OUT_USE
OUT_DISCARD
OUT_LOST
OUT_GIFT
OUT_OTHER
ADJUSTMENT
```

### status

거래 상태.

```text
PENDING
APPROVED
REJECTED
CANCELED
```

### quantity_delta

현재고 계산에 반영되는 증감 수량.

```text
입고와 초기재고는 양수.
출고 계열은 음수.
실사조정은 actual_quantity - expected_quantity.
```

### quantity_input

사용자가 입력한 원래 수량.

```text
입고 10개라면 quantity_input = 10.
사용 2개라면 quantity_input = 2.
초기재고 20개라면 quantity_input = 20.
```

### expected_quantity

실사조정 요청 시점의 시스템 계산 재고.

실사조정이 아닌 거래에서는 null 가능.

### actual_quantity

실사조정 시 사용자가 입력한 실제 재고.

실사조정이 아닌 거래에서는 null 가능.

### occurred_at

실제 입고, 사용, 폐기, 실사조정이 발생한 시점.

### created_at

시스템에 기록이 생성된 시점.

### supplier

해당 거래의 실제 공급업체.

적용 원칙:

```text
IN 거래에서 사용한다.
기본값은 ManagedItem.default_supplier로 자동 채운다.
필요 시 사용자가 다른 공급업체로 변경할 수 있다.
출고, 폐기, 분실, 증정, 실사조정, 초기재고 거래에서는 null 가능하다.
```

### unit_price

입고단가.

v0.1에서는 현재고 계산에 사용하지 않으며, 향후 원가 분석을 위한 참고 데이터로만 저장한다.

### expiration_date

유통기한.

v0.1에서는 알림에 사용하지 않으며, 향후 유통기한 임박 알림을 위한 참고 데이터로만 저장한다.

---

# 8. 고정 선택값과 자유입력 기준

## 8.1 고정 선택값

v0.1에서는 주요 코드값과 필터 기준값이 흔들리지 않도록 일부 필드는 고정 선택값으로 관리한다.

다음 필드는 코드 또는 통제된 선택값으로 관리한다.

```text
role
transaction_type
status
category
unit
```

### role

```text
STAFF
TEAM_LEADER
MANAGER
ADMIN
```

### transaction_type

```text
INITIAL_COUNT
IN
OUT_USE
OUT_DISCARD
OUT_LOST
OUT_GIFT
OUT_OTHER
ADJUSTMENT
```

### status

```text
PENDING
APPROVED
REJECTED
CANCELED
```

### category

v0.1 고정 선택값:

```text
미용소모품
의료용품
위생용품
의약품
일반소모품
전용소모품
기타
```

분류는 자유입력하지 않는다.

### unit

v0.1 고정 선택값:

```text
EA
BOX
PACK
P
ROLL
BOTTLE
VIAL
AMP
ML
G
KG
SET
OTHER
```

단위는 자유입력하지 않는다.

현장에 필요한 단위가 없으면 일단 `OTHER`를 사용하고, 반복적으로 필요하면 선택값에 추가한다.

## 8.2 자유입력값

다음 필드는 v0.1에서 자유입력으로 둔다.

```text
storage_location
memo
specification
```

### storage_location

보관장소는 현장마다 표현이 다양하므로 v0.1에서는 자유입력으로 둔다.

필터 방식:

```text
드롭다운 필터가 아니라 부분일치 검색 또는 텍스트 검색을 기본으로 한다.
```

향후 확장:

```text
v0.2 이후 Location 모델 또는 보관장소 선택값 관리 기능을 검토한다.
```

### specification

규격은 설명용 텍스트다.

계산에는 사용하지 않는다.

### memo

메모는 자유입력한다.

---

# 9. 단위 관리

## 9.1 관리단위 원칙

v0.1에서는 하나의 `ManagedItem`은 하나의 관리단위만 가진다.

```text
ManagedItem.unit
```

입고, 사용, 폐기, 실사조정은 모두 같은 관리단위로 입력한다.

## 9.2 specification과 unit의 차이

`Item.specification`은 설명용이다.

예:

```text
1BOX(10EA)
500mL
1P(100PCS)
```

`ManagedItem.unit`은 계산 기준이다.

예:

```text
BOX
EA
PACK
ROLL
BOTTLE
```

## 9.3 단위 변환 제외

v0.1에서는 박스로 입고하고 낱개로 사용하는 자동 단위 변환을 제공하지 않는다.

운영 기준:

```text
관리단위를 BOX로 정했으면 입고/사용/폐기/실사 모두 BOX 기준으로 입력한다.
관리단위를 EA로 정했으면 입고/사용/폐기/실사 모두 EA 기준으로 입력한다.
```

단위 변환 기능은 v0.2 이후 검토한다.

## 9.4 운영 개시 후 ManagedItem.unit 변경 금지

`ManagedItem.unit`은 재고 계산의 기준 단위다.

운영 개시 후 단위를 변경하면 과거 거래 수량의 의미가 달라질 수 있다.

운영 개시 기준:

해당 `ManagedItem`에 다음 거래 중 하나라도 존재하면 운영이 시작된 것으로 본다.

```text
APPROVED INITIAL_COUNT
APPROVED IN
APPROVED OUT_USE
APPROVED OUT_DISCARD
APPROVED OUT_LOST
APPROVED OUT_GIFT
APPROVED OUT_OTHER
APPROVED ADJUSTMENT
```

운영 개시 후 단위를 바꿔야 하는 경우 기존 `ManagedItem`을 비활성화하고, 새 `ManagedItem`을 생성한다.

```text
기존 ManagedItem → is_active = False
새 ManagedItem → 올바른 unit으로 새로 생성
```

이후 새 `ManagedItem`에 초기재고 또는 실사조정을 통해 기준 재고를 설정한다.

`minimum_stock`, `storage_location`, `default_supplier`, `memo`는 운영 중 변경 가능하다.

단, `unit`은 운영 개시 후 변경하지 않는다.

---

# 10. 화면 구성

## 10.1 Login

기능:

```text
ID/PW 로그인
비활성 사용자 로그인 차단
역할에 따른 홈 화면 분기
```

v0.1에서는 PIN 로그인을 구현하지 않는다.

## 10.2 홈 화면 분기

로그인 후 첫 화면은 역할에 따라 달라진다.

```text
STAFF → Staff Home
TEAM_LEADER → TeamLeader Home
MANAGER → Manager Home
ADMIN → Manager Home 또는 Admin Dashboard
```

`ADMIN`은 일반 운영 화면과 Django Admin 모두 접근할 수 있어야 한다.

## 10.3 Staff Home

대상:

```text
STAFF 이상
```

표시 항목:

```text
내 부서
오늘 내가 등록한 거래 수
내 부서 최소재고 이하 품목 개수
주요 작업 버튼
```

버튼:

```text
입고 등록
출고 등록
현재고 조회
최소재고 이하 품목 보기
거래 이력 보기
실사조정 요청
초기재고 입력 요청
```

## 10.4 TeamLeader Home

대상:

```text
TEAM_LEADER 이상
```

표시 항목:

```text
내 부서 현재고 요약
내 부서 최소재고 이하 품목
내 부서 최근 거래 내역
대기 중인 PENDING 거래
```

버튼:

```text
입고 등록
출고 등록
현재고 조회
최소재고 이하 품목 보기
부서 거래 이력 보기
실사조정 요청
초기재고 입력 요청
```

## 10.5 Manager Home

대상:

```text
MANAGER 이상
```

표시 항목:

```text
전체 부서 현재고 요약
전체 최소재고 이하 품목
부서별 최근 거래 내역
승인 대기 중인 PENDING 거래
```

버튼:

```text
전체 현재고 조회
전체 최소재고 이하 품목 보기
부서별 거래 이력 보기
입고 등록
출고 등록
실사조정 요청
초기재고 입력
PENDING 거래 승인/반려
Django Admin 이동
```

`MANAGER`와 `ADMIN`은 부서 제한 없이 전체 데이터를 조회하고 입력할 수 있다.

v0.1에서는 마스터 데이터 관리와 사용자 관리를 커스텀 화면으로 만들지 않는다.

Manager Home에서는 다음 버튼을 제공하지 않는다.

```text
품목 관리
관리품목 관리
공급업체 관리
사용자 기본 관리
```

대신 Django Admin 이동 버튼을 제공한다.

단, Django Admin 이동 버튼은 사용자가 Django Admin 접근권한을 가진 경우에만 표시한다.

## 10.6 입고 등록 화면

대상:

```text
STAFF 이상
```

입력 항목:

```text
관리품목
입고수량
입고일시
공급업체
유통기한
메모
```

입고단가 표시 기준:

```text
STAFF → 입고단가 필드 숨김
TEAM_LEADER → 입고단가 선택 입력
MANAGER / ADMIN → 입고단가 입력 및 수정 가능
```

규칙:

```text
입고수량은 0보다 커야 한다.
비활성 관리품목은 기본 선택 목록에서 제외한다.
STAFF와 TEAM_LEADER는 본인 부서 관리품목만 선택 가능하다.
MANAGER와 ADMIN은 전체 부서 관리품목을 선택 가능하다.
입고 거래는 저장 즉시 APPROVED 상태가 된다.
quantity_delta는 양수로 저장한다.
공급업체 기본값은 ManagedItem.default_supplier로 표시한다.
사용자는 실제 입고 공급업체가 다르면 변경할 수 있다.
```

공급업체는 선택 입력으로 둘 수 있으나, 가능하면 입력을 권장한다.

유통기한은 재고 안전성과 관련이 있으므로 STAFF도 입력 가능하게 둔다.

## 10.7 출고 등록 화면

대상:

```text
STAFF 이상
```

출고 유형:

```text
사용
폐기
분실
증정
기타출고
```

입력 항목:

```text
관리품목
출고 유형
출고수량
발생일시
메모
```

규칙:

```text
출고수량은 0보다 커야 한다.
현재고보다 많은 수량은 일반 운영 화면에서 저장할 수 없다.
STAFF와 TEAM_LEADER는 본인 부서 관리품목만 선택 가능하다.
MANAGER와 ADMIN은 전체 부서 관리품목을 선택 가능하다.
출고 거래는 저장 즉시 APPROVED 상태가 된다.
quantity_delta는 음수로 저장한다.
```

## 10.8 현재고 조회 화면

대상:

```text
STAFF 이상
```

표시 항목:

```text
부서
품목명
분류
규격
관리단위
보관장소
현재고
최소재고
최소재고 이하 여부
기본 공급업체
```

필터:

```text
부서
분류
보관장소
최소재고 이하 여부
활성 여부
```

권한:

```text
STAFF, TEAM_LEADER → 본인 부서만 조회
MANAGER, ADMIN → 전체 부서 조회
```

보관장소 필터는 드롭다운이 아니라 부분일치 검색 또는 텍스트 검색을 기본으로 한다.

## 10.9 최소재고 이하 품목 화면

대상:

```text
STAFF 이상
```

표시 기준:

```text
현재고 <= 최소재고
```

표시 항목:

```text
부서
품목명
현재고
최소재고
부족 수량
보관장소
기본 공급업체
최근 거래일
```

`부족 수량` 계산:

```text
부족 수량 = 최소재고 - 현재고
```

현재고가 최소재고와 같은 경우 부족 수량은 0이지만 발주 후보로 표시한다.

## 10.10 실사조정 요청 화면

대상:

```text
STAFF 이상
```

입력 항목:

```text
관리품목
실제 수량
발생일시
조정 사유
메모
```

규칙:

```text
시스템은 요청 시점의 현재고를 expected_quantity로 저장한다.
입력한 실제 수량을 actual_quantity로 저장한다.
quantity_delta = actual_quantity - expected_quantity로 계산한다.
생성 시 status = PENDING으로 저장한다.
PENDING 상태에서는 현재고에 반영하지 않는다.
```

권한:

```text
STAFF → 본인 부서 관리품목만 실사조정 요청 가능
TEAM_LEADER → 본인 부서 관리품목만 실사조정 요청 가능
MANAGER, ADMIN → 전체 부서 관리품목에 대해 실사조정 요청 가능
```

승인 권한:

```text
MANAGER 이상만 승인/반려 가능
```

## 10.11 초기재고 입력 화면

대상:

```text
STAFF 이상
```

입력 항목:

```text
관리품목
초기재고 수량
발생일시
메모
```

규칙:

```text
초기재고 수량은 0 이상이어야 한다.
APPROVED INITIAL_COUNT가 이미 존재하는 ManagedItem은 일반 운영 화면에서 INITIAL_COUNT 추가 생성 불가.
PENDING INITIAL_COUNT가 이미 존재하면 경고 표시.
STAFF와 TEAM_LEADER가 생성하면 PENDING 상태로 저장.
MANAGER와 ADMIN이 생성하면 APPROVED 상태로 저장.
```

운영 원칙:

```text
초기재고는 7월 하드리셋 시 실제 실사 결과를 기준으로 입력한다.
초기재고 승인 완료 전에는 해당 ManagedItem의 입출고 운영을 시작하지 않는다.
```

## 10.12 PENDING 거래 승인 큐

기존의 “실사조정 승인/반려 화면”은 “PENDING 거래 승인 큐”로 확장한다.

승인 큐에는 다음 거래가 포함된다.

```text
INITIAL_COUNT
ADJUSTMENT
```

조건:

```text
status = PENDING
```

대상:

```text
MANAGER 이상
```

기능:

```text
PENDING 거래 목록 조회
요청 상세 확인
승인
반려
철회 또는 취소 처리
INITIAL_COUNT 일괄 승인
```

승인 가능 역할:

```text
MANAGER
ADMIN
```

승인 시:

```text
status = APPROVED
approved_by = 현재 사용자
approved_at = 현재 시각
현재고 계산에 반영
```

반려 시:

```text
status = REJECTED
approved_by = 현재 사용자
approved_at = 현재 시각
현재고 계산에 미반영
```

철회 또는 취소 시:

```text
status = CANCELED
canceled_by = 현재 사용자 또는 MANAGER/ADMIN
canceled_at = 현재 시각
현재고 계산에 미반영
```

### 승인 큐 표시 항목

```text
요청일시
발생일시
부서
품목명
거래유형
요청자
시스템 기준 수량
사용자 입력 수량
증감 수량
메모
```

### ADJUSTMENT 표시 기준

`ADJUSTMENT`는 시스템 기준 수량과 실제 수량의 차이를 반영하는 거래다.

표시 항목:

```text
시스템 기준 수량 = expected_quantity
사용자 입력 수량 = actual_quantity
증감 수량 = quantity_delta
```

### INITIAL_COUNT 표시 기준

`INITIAL_COUNT`는 기준 재고를 처음 설정하는 거래다.

`INITIAL_COUNT`에는 기존 시스템 기준 수량 개념이 없다.

표시 항목:

```text
시스템 기준 수량 = 공란 또는 "-"
사용자 입력 수량 = quantity_input
증감 수량 = quantity_delta
```

화면 라벨은 거래 유형에 따라 다르게 표시할 수 있다.

예:

```text
ADJUSTMENT: 시스템 기준 수량 / 실제 수량 / 차이
INITIAL_COUNT: 기준 없음 / 초기재고 수량 / 반영 수량
```

## 10.13 INITIAL_COUNT 일괄 승인

v0.1에서는 초기재고 온보딩 부담을 줄이기 위해 `INITIAL_COUNT` 거래에 한해 일괄 승인 기능을 제공한다.

일괄 승인 가능 조건:

```text
transaction_type = INITIAL_COUNT
status = PENDING
동일 부서 또는 선택된 거래 묶음
승인자 = MANAGER 또는 ADMIN
```

일괄 승인 시 각 거래별로 승인 가능 여부를 개별 검사한다.

승인 시 각 거래에 다음 값이 기록된다.

```text
status = APPROVED
approved_by = 현재 사용자
approved_at = 현재 시각
```

실사조정 `ADJUSTMENT`는 v0.1에서 일괄 승인 대상에 포함하지 않는다.

일괄 승인 결과는 사용자에게 표시한다.

예:

```text
승인 완료: 18건
승인 제외: 2건
제외 사유: 이미 승인된 초기재고가 있음
```

## 10.14 거래 이력 화면

대상:

```text
STAFF 이상
```

표시 항목:

```text
발생일시
입력일시
부서
품목명
거래유형
상태
수량
증감값
입력자
승인자
취소자
공급업체
메모
취소 사유
```

정렬 기준:

```text
occurred_at desc
created_at desc
id desc
```

권한:

```text
STAFF → 본인 부서 거래 이력 읽기 가능
TEAM_LEADER → 본인 부서 전체 거래 조회
MANAGER, ADMIN → 전체 거래 조회
```

거래 취소 버튼 표시 기준:

```text
STAFF → 본인이 당일 등록한 APPROVED 일반 거래에만 취소 버튼 표시
TEAM_LEADER → 본인 부서 당일 APPROVED 일반 거래에만 취소 버튼 표시
MANAGER / ADMIN → 전체 APPROVED 거래에 취소 버튼 표시
```

PENDING 거래 철회 버튼 표시 기준:

```text
거래 생성자 → 본인이 생성한 PENDING 거래에 철회 버튼 표시
MANAGER / ADMIN → 전체 PENDING 거래에 철회 또는 반려 가능
```

## 10.15 Django Admin

대상:

```text
ADMIN
필요 시 MANAGER 일부
```

용도:

```text
사용자 관리
부서 관리
품목 마스터 관리
관리품목 관리
공급업체 관리
거래 원장 확인
예외 데이터 수정
시스템 관리
```

직원과 팀장이 매일 사용하는 화면은 Django Admin이 아니라 일반 운영 화면으로 제공한다.

Django Admin에서 관리하는 항목:

```text
사용자
부서
품목 마스터
부서별 관리품목
공급업체
거래 원장
```

커스텀 운영 화면에서는 마스터 데이터 관리 화면을 별도로 만들지 않는다.

### Admin 접근권한

재고 운영을 담당하는 MANAGER에게는 필요 시 Django Admin 접근권한을 부여한다.

Django Admin 접근에는 Django의 관리자 접근 권한이 필요하다.

운영 기준:

```text
ADMIN은 Django Admin 전체 접근 가능
재고 운영 담당 MANAGER는 제한된 Django Admin 접근 가능
Django Admin 접근권한이 없는 MANAGER에게는 Admin 이동 버튼을 표시하지 않음
```

### Admin 이동 버튼 표시 조건

```text
사용자가 Django Admin 접근권한을 가진 경우에만 표시
```

접근권한이 없는 사용자에게 Admin 이동 버튼을 노출해 접근 거부 화면으로 보내지 않는다.

---

# 11. 하드리셋 운영 방침

## 11.1 기존 데이터 마이그레이션 제외

기존 AppSheet 및 Google Sheets 데이터는 새 시스템으로 이전하지 않는다.

기존 자료는 과거 참고자료로만 보존한다.

새 시스템의 현재고와 기존 시스템의 현재고를 억지로 맞추지 않는다.

## 11.2 7월 기준 새 출발

7월 기준으로 각 파트는 실제 재고를 실사하고, 새 시스템에 초기재고를 직접 입력한다.

이 과정은 단순 입력 작업이 아니라 교육 과정으로 활용한다.

## 11.3 온보딩 순서

v0.1 하드리셋 운영 시 다음 순서를 따른다.

```text
1. 부서 생성
2. 품목 마스터 생성
3. 부서별 관리품목 생성
4. 실제 재고 실사
5. INITIAL_COUNT 입력
6. MANAGER 또는 ADMIN 승인
7. 초기재고 승인 완료 확인
8. 입고/출고 운영 시작
```

초기재고 승인 전에는 해당 ManagedItem의 입고/출고 운영을 시작하지 않는다.

초기재고가 승인되지 않은 품목은 현재고가 0으로 보일 수 있으므로, 운영 시작 전 승인 여부를 반드시 확인한다.

## 11.4 초기재고 등록

초기재고는 `StockTransaction`의 `INITIAL_COUNT` 유형으로 저장한다.

초기재고는 기존 시스템에서 이전하지 않고 실제 실사 결과를 기준으로 입력한다.

초기재고 거래는 MANAGER 또는 ADMIN 승인 후 현재고에 반영된다.

## 11.5 팀장 외 1명 교육

각 파트는 반드시 팀장 외 1명 이상이 다음 업무를 수행할 수 있어야 한다.

```text
입고 등록
출고 등록
현재고 조회
최소재고 이하 품목 확인
실사조정 요청
초기재고 입력 요청
거래 이력 조회
오입력 취소 절차 이해
```

이 원칙은 특정 개인에게 재고관리 지식이 독점되는 것을 막기 위한 필수 운영 원칙이다.

팀장 외 백업 인원이 반드시 TEAM_LEADER일 필요는 없다.

STAFF도 실사조정 요청과 부서 거래 이력 조회가 가능하므로, 백업 인원은 STAFF 권한으로도 기본 재고관리 업무를 수행할 수 있다.

단, 실사조정 승인, 초기재고 승인, 전체 부서 관리는 MANAGER 이상만 가능하다.

## 11.6 실사조정 승인 운영 원칙

v0.1에서는 실사조정 승인 권한을 MANAGER 이상으로 유지한다.

STAFF와 TEAM_LEADER는 실사조정 요청을 생성할 수 있지만, 승인할 수 없다.

승인 권한:

```text
MANAGER
ADMIN
```

실사조정은 승인 전에는 현재고에 반영되지 않는다.

운영 병목을 줄이기 위해 다음 원칙을 둔다.

```text
MANAGER 또는 ADMIN 승인 가능 계정을 최소 2개 이상 둔다.
실사조정 요청은 가급적 당일 승인 또는 반려한다.
MANAGER/ADMIN은 모바일 또는 외부 환경에서도 승인 가능하도록 운영한다.
```

소규모 운영 현실을 고려하여 v0.1에서는 MANAGER의 자가승인을 허용한다.

자가승인이란 MANAGER가 본인이 생성한 실사조정 요청을 직접 승인하는 것을 말한다.

단, 다음 기록은 반드시 남긴다.

```text
created_by
approved_by
approved_at
memo
```

자가승인 제한 또는 이중승인은 v0.2 이후 검토한다.

---

# 12. 입력 누락 여부

v0.1에서는 입력 누락 여부를 판단하지 않는다.

재고관리는 이벤트 기반 업무이므로, 특정 날짜에 입력이 없다고 해서 반드시 누락이라고 볼 수 없다.

예:

```text
입고가 없으면 입고 기록이 없어도 정상이다.
사용이 없으면 출고 기록이 없어도 정상이다.
```

입력 누락 판단은 정기 실사, 일일 마감, 체크리스트 기능과 연결되어야 하므로 v0.2 이후 검토한다.

---

# 13. 날짜와 시간 기준

`StockTransaction`은 다음 두 시각을 가진다.

```text
occurred_at
created_at
```

## 13.1 occurred_at

실제 입고, 사용, 폐기, 분실, 증정, 실사조정이 발생한 시점이다.

직원이 입력할 수 있다.

## 13.2 created_at

시스템에 기록이 생성된 시점이다.

자동 기록된다.

## 13.3 현재고 계산 기준

현재고 계산은 `occurred_at` 순서가 아니라 `APPROVED` 상태 거래의 전체 합계로 계산한다.

```text
현재고 = APPROVED 거래의 quantity_delta 합계
```

동일 일자 내 입고와 출고의 순서는 현재고 합계에는 영향을 주지 않는다.

거래 이력 표시는 다음 순서로 정렬한다.

```text
occurred_at desc
created_at desc
id desc
```

---

# 14. 보안 원칙

v0.1에서는 환자정보를 다루지 않는다.

시스템에 입력하지 않는 정보:

```text
환자명
차트번호
주민등록번호
진료기록
민감한 컴플레인 내용
```

보안 원칙:

```text
직원별 개별 계정을 사용한다.
공용 계정 사용을 지양한다.
퇴사자 또는 비활성 직원은 즉시 비활성화한다.
관리자 권한은 최소 인원에게만 부여한다.
DB 접속정보는 코드에 직접 저장하지 않는다.
개인 Google Sheets 기반 운영을 지양한다.
HTTPS 환경에서 운영한다.
역할 변경과 관리자 권한 부여는 ADMIN만 가능하다.
MANAGER는 자기 자신의 권한을 수정할 수 없다.
```

## 14.1 ADMIN 비상 복구 운영 원칙

역할 변경과 ADMIN 권한 부여는 ADMIN 전용이다.

따라서 ADMIN 계정이 하나뿐이고 접근이 불가능해지면 운영 복구가 어려울 수 있다.

v0.1 운영 원칙:

```text
활성 ADMIN 계정은 최소 2개 이상 둔다.
비상 복구용 superuser 생성 절차를 운영진 문서에 기록한다.
비상 복구 절차는 일반 직원에게 공유하지 않는다.
```

비상 복구 세부 절차는 TECH_SPEC 또는 운영문서에서 별도로 정의한다.

---

# 15. 기술 방향

## 15.1 기본 기술 스택

```text
Backend: Django
Database: PostgreSQL
Frontend: Django Template 기반
Admin: Django Admin
Authentication: Django 기본 인증
```

## 15.2 프론트엔드 원칙

v0.1에서는 React, Next.js 등 별도 프론트엔드 프레임워크를 사용하지 않는다.

이유:

```text
MVP 범위가 커지는 것을 방지한다.
Django 기반 CRUD 화면을 빠르게 구현한다.
직원용 화면을 단순하게 유지한다.
```

필요 시 v0.2 이후 HTMX 또는 별도 프론트엔드 도입을 검토한다.

## 15.3 배포 원칙

배포 환경은 후속 기술명세에서 확정한다.

기본 원칙:

```text
PostgreSQL 사용
환경변수로 설정 관리
HTTPS 적용
개인 Google 계정 의존 제거
```

## 15.4 동시성 처리는 TECH_SPEC에서 정의

현재고 음수 방지 규칙은 다음과 같다.

```text
출고 후 현재고 < 0 이면 저장 불가
거래 취소 후 현재고 < 0 이면 취소 불가
```

다만 두 사용자가 같은 품목에 대해 동시에 출고 또는 취소를 시도할 경우, 단순 조회 후 저장 방식만으로는 음수 재고가 발생할 수 있다.

이 문제는 PRODUCT_SPEC이 아니라 TECH_SPEC에서 구현 방식으로 처리한다.

TECH_SPEC에서 다음 중 하나 이상의 방식을 정의한다.

```text
트랜잭션 처리
저장 직전 현재고 재검증
ManagedItem 단위 row lock
select_for_update 사용
커밋 시점 재검증
```

v0.1은 소규모 사용을 전제로 하지만, 출고·취소 저장 시에는 반드시 현재고를 재검증한다.

## 15.5 TECH_SPEC에서 확정할 주요 구현 항목

PRODUCT_SPEC 이후 TECH_SPEC에서는 다음 구현 사안을 확정한다.

```text
동시성/음수 재검증: ManagedItem 잠금, select_for_update, 커밋 직전 현재고 재계산
INITIAL_COUNT 유일성 enforcement: PostgreSQL 부분 유니크 인덱스 + 애플리케이션 검사
현재고 계산 전략: v0.1에서는 거래 합산 기반, annotate/Sum으로 N+1 방지
고정 선택값 구현: role, transaction_type, status, category, unit → Django TextChoices
unit 변경 금지 enforcement: 운영 개시 판정 후 모델 clean 또는 Admin 가드
권한 게이트: 역할 계층 + 부서 스코프를 View/QuerySet에서 강제
상태 전이 enforcement: 모델 메서드로 허용되지 않은 전이 차단
```

---

# 16. v0.1 완료 기준

## 16.1 기능 기준

v0.1은 다음 기능이 작동하면 완료로 본다.

```text
직원 계정으로 로그인할 수 있다.
역할에 따라 홈 화면이 분기된다.
부서를 생성하고 관리할 수 있다.
품목 마스터를 생성하고 관리할 수 있다.
부서별 관리품목을 생성하고 관리할 수 있다.
초기재고를 입력할 수 있다.
초기재고를 승인/반려할 수 있다.
초기재고를 일괄 승인할 수 있다.
ManagedItem당 APPROVED INITIAL_COUNT는 최대 1건만 허용된다.
INITIAL_COUNT 승인 시점에 유일성 검사가 수행된다.
입고를 등록할 수 있다.
입고 거래에 실제 공급업체를 기록할 수 있다.
출고를 등록할 수 있다.
폐기, 분실, 증정, 기타출고를 구분해 등록할 수 있다.
현재고를 조회할 수 있다.
최소재고 이하 품목을 조회할 수 있다.
STAFF 이상이 실사조정 요청을 생성할 수 있다.
STAFF가 생성한 실사조정 요청은 승인 전 현재고에 반영되지 않는다.
생성자는 본인의 PENDING 거래를 철회할 수 있다.
MANAGER 이상이 PENDING 거래를 승인/반려할 수 있다.
APPROVED 거래만 현재고에 반영된다.
CANCELED 거래는 현재고에 반영되지 않는다.
현재고 초과 출고가 일반 운영 화면에서 차단된다.
현재고가 음수가 되는 거래 취소가 일반 운영 화면에서 차단된다.
STAFF와 TEAM_LEADER는 본인 부서 거래 이력을 읽기 전용으로 조회할 수 있다.
category와 unit은 통제된 선택값으로 관리된다.
storage_location은 자유입력이며 부분일치 검색으로 조회한다.
운영 개시 후 ManagedItem.unit 변경을 금지한다.
```

## 16.2 운영 기준

v0.1은 다음 운영 조건을 만족하면 완료로 본다.

```text
피부실(스킨앤라인) 또는 치료실 중 최소 1개 파트에서 실제 사용 가능하다.
해당 파트의 품목 마스터와 관리품목이 새 시스템에 등록되어 있다.
해당 파트의 초기재고가 새 시스템에 등록되어 있다.
해당 파트의 초기재고가 승인되어 있다.
초기재고 승인 완료 후 입고/출고 운영을 시작한다.
팀장 외 1명 이상이 입고/출고/조회/실사조정 요청/오입력 취소 방법을 익힌다.
최소 1주일간 입고/출고/폐기 기록을 남긴다.
운영진이 최소재고 이하 품목을 확인할 수 있다.
기존 AppSheet 없이도 해당 파트의 재고 흐름을 파악할 수 있다.
MANAGER 또는 ADMIN 승인 가능 계정이 최소 2개 이상 존재한다.
활성 ADMIN 계정이 최소 2개 이상 존재한다.
```

## 16.3 완료로 보지 않는 경우

다음 상태라면 v0.1 완료로 보지 않는다.

```text
관리자만 쓸 수 있고 직원이 입력할 수 없다.
현재고가 수동 입력값으로만 관리된다.
입고와 출고 이력이 남지 않는다.
실사조정이 기록 없이 숫자만 수정된다.
팀장 1명만 사용법을 알고 있다.
STAFF가 재고 불일치 상황에서 아무 요청도 남길 수 없다.
STAFF가 부서 거래 이력을 볼 수 없어 백업 역할을 수행할 수 없다.
잘못 입력한 거래를 현장에서 취소할 수 없다.
최소재고 이하 품목을 확인할 수 없다.
기존 Google Sheets를 계속 병행해야만 현재고를 알 수 있다.
초기재고가 중복 승인될 수 있다.
```

---

# 17. 향후 확장 후보

## 17.1 v0.2 후보

```text
부서별 마감보고
공지 확인
발주 요청 기능
발주 완료 처리
유통기한 임박 알림
정기 실사 주기 관리
입력 누락 판단
HTMX 기반 사용성 개선
보관장소 Location 모델화
MANAGER 사용자 기본 관리 커스텀 기능
자가승인 제한 또는 이중승인
```

## 17.2 v0.3 후보

```text
치료실 재고 확대
탕전실 재고 검토
비품/장비 자산관리
폐기 사유 분석
부서별 소모량 리포트
단위 변환 기능
```

## 17.3 v1.0 후보

```text
김포365 Staff 통합
컴플레인 접수
교육 이수 관리
운영진 대시보드
Notion HQ와 일부 연동
시술/처방별 소모량 분석
```

---

# 18. 프로젝트 성공 기준

`gimpo365-inventory` v0.1의 성공 기준은 프로그램이 멋있게 완성되는 것이 아니다.

성공 기준은 다음과 같다.

```text
재고관리 방식이 특정 개인에게 묶이지 않는다.
팀장 외 1명 이상이 동일한 방식으로 업무를 수행한다.
운영진이 부족 품목을 감각이 아니라 데이터로 확인한다.
입고, 사용, 폐기, 실사조정, 초기재고, 취소의 흔적이 남는다.
직원은 어렵지 않게 입력한다.
STAFF도 재고 불일치 상황을 시스템에 요청으로 남길 수 있다.
STAFF도 본인 부서 거래 이력을 읽고 백업 업무를 수행할 수 있다.
오입력은 삭제가 아니라 취소 이력으로 남긴다.
팀장은 부서 재고 흐름을 확인한다.
운영진은 전체 재고 상태를 판단한다.
7월 이후 새 기준으로 재고관리가 시작된다.
```

이 프로젝트는 김포365OS 전체의 완성이 아니라, 사람에게 의존하던 운영 업무를 시스템으로 옮기는 첫 번째 모듈이다.

---

## 부록 P. 주문서-입고 반자동화 (v0.2.1)

- 주문서 = 입고 예정 기록(현재고 불변). 실제 재고 증가는 입고등록으로만 발생.
- 입고등록은 주문 품목(OrderItem) 단위. 부분입고 가능, 주문 상태(주문완료/부분입고/입고완료) 자동 계산.
- 주문수량 초과 입고 차단 → 초과분은 일반 입고등록 + 메모('추가증정' 등).
- 입고 단가 필수(>0), 유통기한 필수('유통기한 없음' 선택 시 입고일+3년 자동).
- 잔여수량 취소 기능은 이번 버전 미구현(미입고 잔여는 계속 표시, 사유는 메모).
- 재고현황+최소재고 통합, MANAGER/ADMIN 부서 필터(STAFF/TL 미노출·범위 불변), 2시간 자동 로그아웃.
- 상세 운영 절차는 OPERATIONS_SETUP.md §6B~6D.
