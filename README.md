# gimpo365-inventory

김포365한의원 내부 재고관리 시스템 **v0.1** (개발자용 입구 문서).

김포365OS의 첫 번째 독립 모듈로, 소모품·의료용품·미용소모품·위생용품·의약품·일반소모품의
재고를 표준화된 방식으로 관리한다.

## 문서 지도

| 문서 | 대상 | 용도 |
|---|---|---|
| **README.md** (이 문서) | 개발자 | 로컬 개발 환경, 실행, 테스트 |
| [OPERATIONS_SETUP.md](OPERATIONS_SETUP.md) | 운영자 | 운영 서버 초기 세팅·계정·비상 복구 |
| [MANUAL_QA_CHECKLIST.md](MANUAL_QA_CHECKLIST.md) | 운영자/QA | 운영 투입 전 수동 점검 |
| [PRODUCT_SPEC.md](PRODUCT_SPEC.md) | 전체 | 제품·운영 기준 명세 |
| [TECH_SPEC.md](TECH_SPEC.md) | 개발자 | 구현 기준 명세 |
| [TASKS.md](TASKS.md) | 개발자 | 작업 순서·진행 상태 |

## 기술 스택

| 구분 | 선택 |
|---|---|
| Backend | Django 6.0 |
| Database | **PostgreSQL** (SQLite 사용 안 함) |
| Frontend | Django Template |
| Admin | Django Admin (ADMIN 전용) |
| Auth | Django 기본 인증 + `accounts.User`(AbstractUser) |

## 프로젝트 구조

```text
gimpo365inventory/
  manage.py
  config/      # Django 설정, root URL, 환경변수
  core/        # 공통 모델 (Department), 공통 fixture(factory)
  accounts/    # Custom User, 역할(Role), 권한 헬퍼
  inventory/   # 품목/관리품목/거래원장, selector·service·permission, forms, views, admin
  templates/
  static/
  requirements.txt
  .env.example
```

핵심 설계(자세히는 [TECH_SPEC.md](TECH_SPEC.md)):

- 현재고 = `APPROVED` 거래의 `quantity_delta` 합계 (별도 수량 필드 없음)
- 재고 거래(`StockTransaction`) 생성·상태변경은 **오직 `inventory/services.py`** 로만 수행
- 조회는 `inventory/selectors.py`, 권한은 `inventory/permissions.py`

## 로컬 개발 환경 설정

### 1. 가상환경 / 의존성

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. 환경변수

`.env.example` 을 `.env` 로 복사한 뒤 값을 채운다.

```powershell
Copy-Item .env.example .env
```

`.env` 항목: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`,
`POSTGRES_DB/USER/PASSWORD/HOST/PORT`. (값 미설정 시 개발용 기본값 사용)

### 3. PostgreSQL

PostgreSQL 이 설치되어 있어야 한다. **SQLite 는 사용하지 않는다.**
`.env` 의 `POSTGRES_*` 와 일치하는 DB 를 준비한다.

```sql
CREATE DATABASE gimpo365_inventory;
```

### 4. 마이그레이션 / 실행

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser   # role=ADMIN 강제 (최소 2개 권장)
.\.venv\Scripts\python.exe manage.py runserver
```

접속: `http://127.0.0.1:8000/` (로그인 → 역할별 대시보드) / `/admin/` (ADMIN 전용)

## 테스트

테스트는 **반드시 PostgreSQL** 에서 실행한다. SQLite 테스트 결과는 완료 기준으로
인정하지 않는다. (TECH_SPEC §15)

```powershell
# PowerShell 에서 (DB 비밀번호가 .env 와 다르면 환경변수로 주입)
$env:PGPASSWORD="postgres"
.\.venv\Scripts\python.exe manage.py test
```

- 테스트 DB(`test_gimpo365_inventory`)는 러너가 자동 생성/삭제한다.
- 가드 테스트 `core.tests.DatabaseEngineTest` 가 테스트 DB 가 PostgreSQL 인지 검증한다.
- 현재 자동 테스트: **147건** (모델/제약·selector·service·permission·form·view·admin).

> SQLite 로는 테스트하지 않는다. `settings.DATABASES` 의 ENGINE 은 PostgreSQL 로 고정되어 있다.

## 개발 원칙 (요약)

- `StockTransaction` 생성·상태변경은 **service 함수로만**. View/Form/Admin 직접 `create()`/`status` 변경 금지.
- 현재고는 계산값(별도 저장 안 함). 출고·취소 시 row lock 후 현재고 재검증으로 음수 방지.
- 오입력은 삭제가 아니라 `CANCELED` 상태로 이력 보존.
- 자세한 금지사항: [TASKS.md](TASKS.md) §0, [TECH_SPEC.md](TECH_SPEC.md) §3.

## 운영 투입

운영 서버 초기 세팅과 계정/비상 복구는 [OPERATIONS_SETUP.md](OPERATIONS_SETUP.md),
투입 전 점검은 [MANUAL_QA_CHECKLIST.md](MANUAL_QA_CHECKLIST.md) 를 따른다.
