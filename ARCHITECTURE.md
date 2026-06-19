# gimpo365-inventory 아키텍처 / 장기 확장 방향

문서 상태: 방향성 정리 (v0.1 안정화 단계).
이 문서는 **현재 구조**와, 장기적으로 **김포365한의원 인트라넷 / 원내 업무 포털**로
확장할 때의 **분리 원칙**을 기록한다. 지금 당장 확장 기능을 구현하지 않는다.

---

## 1. 현재 범위 (v0.1)

- v0.1 의 대상은 **재고관리**다. 그 외 업무 기능(게시판/문서함/체크리스트/근태/연차/인사)은
  포함하지 않는다.
- 현재 우선순위: 재고관리 핵심 안정화 → 원내 알파테스트 → 직원 피드백 → v0.1.1 사용성 개선
  → 그 이후 확장 검토. (자세한 일정 감각은 [ROADMAP.md](ROADMAP.md))

## 2. 장기 방향 (확장 가능성)

이 시스템은 단일 재고 프로그램에 머무르지 않고, 장기적으로 원내 인트라넷의
**첫 번째 업무 모듈**로 확장될 수 있다. 화면상으로는 하나의 원내 업무 포털처럼 보이되,
**내부 구현은 모듈(앱)별로 분리**한다.

향후 후보 모듈 (지금 구현하지 않음):

```text
board       원내 공지사항 / 게시판
docs        업무 매뉴얼 / SOP / 교육자료
checklists  일일점검 / 마감점검 / 장비점검
leave       연차신청 / 휴가승인
attendance  근태기록
hr          면담기록 / 인사메모 / 평가자료
```

## 3. 앱 구조와 책임

```text
config     Django 설정, root URL, 환경변수
core       공통 기반: 부서(Department) 등 공통 모델 / 공통 정책
accounts   공통 계정: Custom User, 역할(Role), 재직 상태, 공통 권한 helper
inventory  재고관리 도메인 전용 (모델/selector/service/permission/form/view/admin)
```

현재(v0.1) 기준 **공통 기반(core, accounts)** 과 **도메인(inventory)** 이 이미 분리되어 있다.

- `accounts.User` 는 inventory 를 import 하지 않는다 → 인트라넷 공통 사용자로 재사용 가능.
- `accounts.permissions` 의 역할 helper(`has_role_at_least`, `is_manager_or_above`,
  `is_admin_role`)는 **공통 권한**이다.
- `inventory.permissions` 의 `can_access_managed_item`, `can_cancel_transaction` 은
  **재고 도메인 전용**이다.
- 공통 레이아웃 템플릿(`base.html`, `navbar.html`, `messages.html`)은 도메인 비종속이다.

## 4. 확장 설계 원칙

1. 공통 계정/부서/권한은 `accounts`, `core` 에서 관리한다.
2. 재고관리 도메인은 `inventory` 앱에만 둔다.
3. 향후 게시판/문서함/체크리스트/근태/연차/인사는 `inventory` 에 넣지 않고 **별도 앱**으로 분리한다.
   (예: `board`, `docs`, `checklists`, `leave`, `attendance`, `hr`)
4. 화면은 하나의 포털처럼 보이되 내부 구현은 모듈별로 분리한다.
5. 새 기능이 생겨도 **`StockTransaction` 원장 원칙과 재고 service 계층 원칙을 침범하지 않는다.**
   (원장 생성/상태변경은 `inventory/services.py` 로만 — TECH_SPEC §0)
6. 현재 재고관리 로직을 "범용 업무 시스템"으로 억지 리팩터링하지 않는다.
7. 확장 가능성은 문서화하되, 지금은 재고관리 안정화가 우선이다.

### 새 모듈을 추가할 때 (향후 가이드)

```text
- core/accounts 의 공통 User/Department/Role/권한 helper 를 재사용한다.
- 새 도메인 모델·로직은 새 앱에 둔다 (inventory 를 건드리지 않는다).
- 화면 진입은 공통 base.html 을 extend 하고, URL 은 앱별 namespace 로 분리한다.
- 권한은 공통 역할 helper + 모듈별 도메인 권한 함수로 구성한다.
```

## 5. 구조 점검 결과 (현재 코드)

| 점검 항목 | 결과 |
|---|---|
| accounts.User 가 inventory 전용 의존성을 갖는가 | **아니오** (inventory import 없음) — 공통 사용자로 적합 |
| core.Department 가 재고 전용으로 과하게 제한되는가 | 대체로 공통. 단, 아래 관찰점 1건 |
| base/navbar/dashboard 이름이 inventory 전용으로 고정됐는가 | base/navbar/messages 는 공통. dashboard 는 `inventory` namespace |
| 권한 helper 의 공통/도메인 분리 | **이미 분리됨** (accounts=공통, inventory=도메인) |

### 관찰점 / 향후 제안 (지금 변경하지 않음)

1. **`core.Department.active_for_inventory`** — 공통 모델(core)에 재고 전용 플래그가 있다.
   v0.1 에서는 문제없으나, 모듈이 늘어나면 "모듈별 활성화" 개념으로 일반화하는 것을 검토할 수 있다.
   (예: 부서-모듈 매핑 또는 모듈별 enable 플래그) — **현 시점 변경 없음, 제안만 기록.**
2. **포털 랜딩** — 현재 루트(`/`)는 inventory 대시보드로 이동한다. 모듈이 늘어나면 모듈 선택이 가능한
   공통 포털 홈을 `core` 등에 두는 구성을 검토할 수 있다. — **현 시점 변경 없음.**
3. 위 항목들은 **코드 변경이 필요하다고 판단되면 별도 제안으로 다룬다.** 이번 문서화에서는 코드 미변경.

## 6. 침범하면 안 되는 것 (재확인)

```text
- StockTransaction 생성/상태변경은 inventory/services.py 로만.
- View/Form/Admin 에서 StockTransaction.objects.create() / status 직접 변경 금지.
- 안정화된 재고 service/selectors/forms/views 흐름을 임의 변경 금지.
- 테스트 없이 구조 변경 금지. (PostgreSQL 테스트 유지)
```

자세한 구현 기준은 [TECH_SPEC.md](TECH_SPEC.md), 제품 기준은 [PRODUCT_SPEC.md](PRODUCT_SPEC.md).
