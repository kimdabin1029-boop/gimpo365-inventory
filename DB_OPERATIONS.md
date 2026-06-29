# gimpo365-inventory DB 백업 / 복구 운영 가이드

배포 전 운영 준비 문서. PostgreSQL 데이터베이스의 **백업과 복구 기본 절차**를 정리한다.
일반 개발은 [README.md](README.md), 운영 초기 세팅은 [OPERATIONS_SETUP.md](OPERATIONS_SETUP.md) 참고.

> 보안 원칙
> - **실제 DB 비밀번호를 스크립트/코드에 저장하지 않는다.**
> - `.env` 는 **절대 커밋하지 않는다.** (비밀번호는 실행 시 입력하거나 운영자가 직접 환경변수로 주입)

---

## 0. 준비물

```text
- PostgreSQL 클라이언트 도구(pg_dump / pg_restore). 보통 PostgreSQL 설치 시 함께 설치된다.
  기본 경로 예: C:\Program Files\PostgreSQL\17\bin
- 백업 저장 폴더: OneDrive\gimpo365_inventory_backups\db
  (스크립트가 없으면 자동 생성한다)
```

---

## 1. 백업 (backup_inventory.ps1)

스크립트: [scripts/backup_inventory.ps1](scripts/backup_inventory.ps1)
PostgreSQL 커스텀 포맷(`pg_dump -Fc`)으로 백업한다. (압축 + `pg_restore` 로 선택 복구 가능)

### 실행

```powershell
# 기본 실행 (DB명/사용자/호스트/포트/PgBin 기본값 사용)
.\scripts\backup_inventory.ps1

# PostgreSQL 설치 버전이 17 이 아니거나 경로가 다르면 -PgBin 지정
.\scripts\backup_inventory.ps1 -PgBin "C:\Program Files\PostgreSQL\16\bin"

# 접속 정보를 다르게 줄 때
.\scripts\backup_inventory.ps1 -DbName gimpo365_inventory -DbUser postgres -DbHost 127.0.0.1 -DbPort 5432
```

### 비밀번호 입력 (코드에 저장하지 않음)

```text
- 실행 시 PostgreSQL 비밀번호를 물어보면 입력한다(화면에 표시되지 않는 SecureString 입력).
- 자동화/스케줄 실행 시에는 실행 직전에 환경변수로 주입할 수 있다:
    $env:PGPASSWORD = "<운영자가 직접 입력>"
    .\scripts\backup_inventory.ps1
  (이 값은 세션 환경변수일 뿐이며, 파일/리포지토리에 저장하지 않는다.)
```

### 저장 위치 / 파일명

```text
OneDrive\gimpo365_inventory_backups\db\gimpo365_inventory_YYYYMMDD_HHmmss.dump
예) gimpo365_inventory_20260622_021530.dump
```

### 스크립트가 자동으로 확인하는 것

```text
1) pg_dump 종료 코드 확인 (실패 시 중단)
2) 백업 파일 크기 확인 (MB / bytes 출력, 0 바이트면 오류 처리)
3) pg_restore -l 로 백업 파일 읽기 검증 (TOC 항목 수 출력) — 실제 복구는 하지 않음
```

### 수동으로 확인하려면

```powershell
# 파일 크기
Get-Item "OneDrive\gimpo365_inventory_backups\db\<파일명>.dump" | Select-Object Length

# 백업 파일이 정상적으로 읽히는지(목차 확인). 실제 복구 아님.
& "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" -l "<백업파일경로>.dump"
```

`pg_restore -l` 이 테이블/시퀀스 등 목록(TOC)을 출력하면 백업 파일이 정상이다.

---

## 2. 복구 (restore)

> ⚠️ 복구는 데이터를 덮어쓴다. 운영 DB 에 복구할 때는 반드시 사전 백업 후, 점검 시간에 수행한다.

커스텀 포맷(`.dump`)은 `pg_restore` 로 복구한다.

### 2.1 새(빈) 데이터베이스로 복구

```powershell
$env:PGPASSWORD = "<운영자 입력>"
# 빈 DB 생성
& "C:\Program Files\PostgreSQL\17\bin\createdb.exe" -U postgres -h 127.0.0.1 gimpo365_inventory_restore
# 백업 파일을 새 DB 로 복구
& "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" -U postgres -h 127.0.0.1 -d gimpo365_inventory_restore "<백업파일경로>.dump"
```

### 2.2 기존 DB 를 백업 시점으로 되돌리기 (전체 교체)

```text
1) 현재 상태를 먼저 백업한다 (위 1번).
2) 애플리케이션(runserver/서비스)을 중지해 접속을 끊는다.
3) 기존 DB 를 드롭하고 다시 만든 뒤 복구한다:
```

```powershell
$env:PGPASSWORD = "<운영자 입력>"
$bin = "C:\Program Files\PostgreSQL\17\bin"
& "$bin\dropdb.exe"   -U postgres -h 127.0.0.1 gimpo365_inventory
& "$bin\createdb.exe" -U postgres -h 127.0.0.1 gimpo365_inventory
& "$bin\pg_restore.exe" -U postgres -h 127.0.0.1 -d gimpo365_inventory "<백업파일경로>.dump"
```

```text
4) 복구 후 애플리케이션을 다시 시작하고, 로그인/재고현황/거래이력이 정상인지 확인한다.
   (필요 시 python manage.py migrate 로 마이그레이션 상태를 맞춘다)
```

---

## 3. 운영 권장 사항

```text
- 정기 백업: 최소 일 1회 (업무 마감 후). Windows 작업 스케줄러로 backup_inventory.ps1 등록 가능.
- 보관: OneDrive 동기화로 원격 보관. 최근 N개만 남기고 오래된 백업 정리(보존 정책)는 운영 결정.
- 백업 검증: 주기적으로 pg_restore -l 로 읽기 확인, 가끔은 임시 DB 로 실제 복구 테스트.
- 비밀번호/.env: 코드·리포지토리에 저장하지 않는다. .env 는 .gitignore 대상이다.
- 복구 절차는 운영진 문서로만 공유한다.
```

## 4. 거래 데이터 정리 (삭제 도구) 주의

```text
- 운영 중 거래 기록은 물리 삭제하지 않는다. 오입력은 "취소(CANCELED)" 이력으로 남긴다.
  (입고 오류는 취소 후 재등록 — OPERATIONS_SETUP.md §6A.2)
- 거래기록 일괄 삭제는 DEBUG 전용 management command 로만 가능하며 운영(DEBUG=False)에서는 거부된다:
    - reset_alpha_data            : 거래 + 마스터(품목/관리품목/공급업체)까지 삭제 (알파 teardown)
    - reset_training_transactions : StockTransaction 만 삭제, 공급업체/품목/관리품목/부서/사용자 유지
                                    (알파/교육용. 기본 dry-run, --yes 시 삭제, --from/--to 기간 필터)
- 두 명령 모두 실제 운영 중 사용 금지. 상세는 OPERATIONS_SETUP.md §1B 참조.
- 삭제로 거래기록을 정리하기 전에는 위 1~2 의 백업을 먼저 수행한다.
```
