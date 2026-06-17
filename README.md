# gimpo365-inventory

김포365한의원 내부 재고관리 시스템 **v0.1**.

김포365OS의 첫 번째 독립 모듈로, 소모품·의료용품·미용소모품·위생용품·의약품·일반소모품의
재고를 표준화된 방식으로 관리한다. 자세한 배경과 범위는 [PRODUCT_SPEC.md](PRODUCT_SPEC.md),
구현 기준은 [TECH_SPEC.md](TECH_SPEC.md), 작업 순서는 [TASKS.md](TASKS.md)를 따른다.

## 기술 스택

| 구분 | 선택 |
|---|---|
| Backend | Django 6.0 |
| Database | PostgreSQL (SQLite 사용 안 함) |
| Frontend | Django Template |
| Admin | Django Admin |
| Auth | Django 기본 인증 + `accounts.User`(AbstractUser) |

## 프로젝트 구조

```text
gimpo365inventory/
  manage.py
  config/      # Django 설정, root URL, 환경변수
  core/        # 공통 모델 (Department)
  accounts/    # Custom User, 역할, 권한 헬퍼
  inventory/   # 품목, 관리품목, 거래원장, 재고 로직, 화면, 폼, Admin
  templates/
  static/
  requirements.txt
  .env.example
```

## 로컬 개발 환경 설정

### 1. 가상환경 / 의존성

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. 환경변수

`.env.example`을 `.env`로 복사한 뒤 값을 채운다.

```powershell
Copy-Item .env.example .env
```

### 3. PostgreSQL

PostgreSQL이 설치되어 있어야 한다. (SQLite는 사용하지 않는다.)
`.env`의 `POSTGRES_*` 값과 일치하는 데이터베이스를 준비한다.

```sql
CREATE DATABASE gimpo365_inventory;
```

### 4. 마이그레이션 / 실행

> 주의: `AUTH_USER_MODEL`(`accounts.User`) 확정 전에는 `migrate`를 실행하지 않는다.
> (TASK 02에서 Custom User 확정 후 첫 migration 수행)

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

## 테스트

테스트는 **반드시 PostgreSQL**에서 실행한다. SQLite 테스트 결과는 완료 기준으로 인정하지 않는다.
(TECH_SPEC §15)

## 개발 원칙 (요약)

- 재고 거래(`StockTransaction`) 생성·상태변경은 **오직 `inventory/services.py`** 를 통해서만 수행한다.
- View/Form/Admin에서 `StockTransaction`을 직접 생성/수정하지 않는다.
- 현재고는 별도 필드가 아니라 `APPROVED` 거래의 `quantity_delta` 합계로 계산한다.

자세한 금지사항은 [TASKS.md](TASKS.md) §0 및 [TECH_SPEC.md](TECH_SPEC.md) §3 참조.
