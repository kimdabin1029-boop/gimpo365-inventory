# gimpo365-inventory v0.1 운영자 초기 설정 가이드 (OPERATIONS SETUP)

이 문서는 **운영자/운영진**이 새 재고관리 시스템을 처음 세팅하고 운영에 투입하기까지의
절차를 정리한 가이드다. 가능한 한 비개발자도 따라갈 수 있게 작성했다.
개발/로컬 실행은 [README.md](README.md), 투입 전 점검은 [MANUAL_QA_CHECKLIST.md](MANUAL_QA_CHECKLIST.md)
를 참고한다.

> 핵심 원칙: **7월 기준 하드리셋**. 기존 AppSheet/Google Sheets 데이터는 옮기지 않고,
> 실제 실사 결과로 새 시스템에 초기재고를 입력해 새 기준으로 시작한다. (PRODUCT_SPEC §11)

---

## 0. 준비물

```text
- 운영 서버 (PostgreSQL 설치, HTTPS 적용 권장)
- 서버 접속 권한 (배포/명령 실행 담당자)
- 적용 파트 결정: 피부실(스킨앤라인) 또는 치료실 중 최소 1개
- 각 파트 실사 인원 (팀장 외 1명 이상)
```

## 1. 시스템 기동 (배포 담당자)

자세한 명령은 [README.md](README.md) 참조. 요약:

```text
1) 환경변수(.env) 설정: SECRET_KEY, ALLOWED_HOSTS, POSTGRES_*  (DB 비밀번호는 코드에 두지 않는다)
2) PostgreSQL 데이터베이스 생성
3) python manage.py migrate
4) HTTPS 환경에서 서비스 기동
```

> DB 는 PostgreSQL 만 사용한다. SQLite 는 사용하지 않는다.

## 1A. 원내 네트워크(LAN)에서 테스트 접속하기

> ⚠️ 이 방식은 **원내 제한 테스트용**이다. 실제 운영 배포는 별도 구성이 필요하다.
> (HTTPS, WSGI/ASGI 서버(gunicorn/uvicorn) + 리버스 프록시(nginx 등), 정적 파일 collectstatic,
>  DEBUG=False, 보안 설정. 9번 항목 참고) `runserver` 는 개발/테스트용 서버다.

### 1A.1 127.0.0.1 의 의미

```text
- 127.0.0.1 (= localhost) 는 "그 PC 자기 자신"만 가리키는 주소다.
- 따라서 python manage.py runserver (기본 127.0.0.1:8000) 로 띄우면
  서버를 띄운 그 PC 에서만 접속되고, 원내 다른 PC 에서는 접속할 수 없다.
- 다른 PC 에서 접속하려면 모든 인터페이스(0.0.0.0)로 바인딩해야 한다.
```

### 1A.2 원내 테스트 실행 명령

```text
python manage.py runserver 0.0.0.0:8000
```

- `0.0.0.0:8000` 은 서버 PC 의 모든 네트워크 인터페이스에서 8000 포트로 접속을 받는다.
- 가상환경 사용 시: `.\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000`

### 1A.3 서버 PC 의 내부 IP 확인 (Windows)

```text
1. 명령 프롬프트(cmd) 또는 PowerShell 실행
2. ipconfig  입력
3. 현재 사용하는 어댑터(예: "이더넷" 또는 "Wi-Fi")의
   "IPv4 주소" 를 확인한다.  예) 192.168.0.25
```

(PowerShell 대안: `ipconfig | findstr IPv4`)

### 1A.4 다른 PC 에서 접속하는 주소

```text
http://<서버PC_IP>:8000/
예) http://192.168.0.25:8000/
```

- 접속하는 PC 와 서버 PC 가 **같은 원내 네트워크(같은 공유기/스위치)** 에 있어야 한다.

### 1A.5 ALLOWED_HOSTS 에 서버 IP 허용

Django 는 `ALLOWED_HOSTS` 에 없는 호스트로 접속하면 차단(400)한다. `.env` 의
`DJANGO_ALLOWED_HOSTS` 에 **서버 PC 의 내부 IP** 를 추가한다.

```text
# .env  (쉼표로 구분)
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,192.168.0.25
```

- IP 가 바뀌면(공유기 재시작 등) 값도 갱신한다. 고정이 필요하면 공유기에서 고정 IP 할당.
- `.env` 의 `DJANGO_DEBUG=True` 인 테스트 환경 기준이다.

### 1A.6 Windows 방화벽에서 8000 포트 허용

처음 `runserver 0.0.0.0:8000` 실행 시 Windows 방화벽 경고가 뜨면 **개인 네트워크 허용**을
체크한다. 수동 설정이 필요하면(관리자 권한 PowerShell):

```text
netsh advfirewall firewall add rule name="gimpo365 inventory 8000" dir=in action=allow protocol=TCP localport=8000
```

- 회사/도메인 네트워크 환경이면 해당 프로필도 허용이 필요할 수 있다.
- 테스트 종료 후 규칙을 제거하려면:
  `netsh advfirewall firewall delete rule name="gimpo365 inventory 8000"`

### 1A.7 접속이 안 될 때 점검

```text
- 서버 PC 와 클라이언트 PC 가 같은 네트워크인지
- runserver 가 0.0.0.0:8000 으로 떠 있는지 (127.0.0.1 이 아님)
- .env 의 DJANGO_ALLOWED_HOSTS 에 서버 IP 가 포함됐는지 (400 이면 이 항목)
- Windows 방화벽에서 8000 포트가 허용됐는지 (접속 자체가 안 되면 이 항목)
- 백신/엔드포인트 보안 SW 가 포트를 막고 있지 않은지
```

## 1B. 알파테스트 데이터 초기화 (DEBUG 전용)

> ⚠️ **운영 환경에서 사용 금지.** 이 절차는 알파테스트 데이터를 비우기 위한 **비운영 teardown**
> 이다. `DEBUG=False`(운영) 환경에서는 `reset_alpha_data` 명령이 **무조건 거부**된다.
> 거래 기록은 운영에서 **삭제하지 않는다**(오입력은 취소/철회). 이 명령은 그 원칙과 별개의
> 테스트 전용 도구다.

### 왜 Admin 에서 StockTransaction delete 를 열지 않는가

```text
- 재고 거래(원장)는 운영에서 물리 삭제하지 않는다. 오입력은 "취소(CANCELED)" 이력으로 남긴다.
  (PRODUCT_SPEC §6.1 / TECH_SPEC §0) → Admin add/delete 는 계속 닫아 둔다.
- 알파테스트 데이터 정리는 운영 경로가 아니라, DEBUG 전용 management command 로만 수행한다.
- 이 명령은 PROTECT FK 를 깨지 않고(자식→부모 순서로 삭제), service/Admin/모델을 변경하지 않는다.
```

### reset_alpha_data 명령

기본 동작: **StockTransaction → ManagedItem → Item → Supplier 삭제.**
유지: **Department(전체), User(전체), superuser/ADMIN.** (사용자/부서 구조는 그대로)

```text
# 삭제 전 미리보기 (실제 삭제 없음)
python manage.py reset_alpha_data --dry-run

# 재고 데이터 초기화 (확인 프롬프트: RESET 입력)
python manage.py reset_alpha_data

# 확인 프롬프트 생략
python manage.py reset_alpha_data --yes

# 테스트 사용자까지 삭제 (username 이 test_ 로 시작하거나 _test 로 끝나는 계정만,
# superuser / ADMIN 은 어떤 경우에도 삭제하지 않음)
python manage.py reset_alpha_data --yes --delete-test-users
```

가드:

```text
- DEBUG=False → 즉시 CommandError 로 중단 (운영 보호)
- --yes 없으면 'RESET' 입력 확인 요구
- --dry-run 은 삭제 대상/건수만 출력
- 실행 후 삭제 건수 요약 출력
```

### 전체 DB 초기화가 필요한 경우 (대안)

품목/거래 ID 까지 1 부터 새로 시작하거나 스키마째 비우려면:

```text
# (A) 모든 데이터 비우기(시퀀스 리셋 포함). superuser 도 삭제되므로 이후 재생성 필요.
python manage.py flush

# (B) DB 를 통째로 다시 만들기 (가장 깨끗)
#   PostgreSQL 에서 DB drop & create 후
python manage.py migrate
```

### 초기화 후 확인

```text
- reset_alpha_data 는 ADMIN/부서를 유지하므로 보통 추가 작업이 필요 없다.
- flush / drop-create 를 했다면 createsuperuser 로 ADMIN 을 다시 만든다.
- 어느 경우든 활성 ADMIN 계정이 최소 2개인지 확인한다. (PRODUCT_SPEC §14.1)
```

### seed_alpha_inventory — 알파테스트 기본 데이터 생성 (DEBUG 전용)

> ⚠️ **운영 환경 사용 금지.** 실제 운영 데이터 세팅용이 아니라 **알파테스트용 샘플 데이터**다.
> 부서/테스트 사용자/공급업체/품목/관리품목/초기재고를 한 번에 만든다.
> 초기재고는 **기존 service(`request_initial_count`)** 로 생성되어 APPROVED 로 현재고에 반영된다.
> 테스트 데이터는 username `_test` 접미, 공급업체/품목명 `[테스트]` prefix 로 표시되어
> `reset_alpha_data --delete-test-users` 와 호환된다.

```text
# 생성 예정 미리보기 (실제 생성 없음)
python manage.py seed_alpha_inventory --dry-run

# 전체(피부실+치료실) 생성 (확인: SEED 입력)
python manage.py seed_alpha_inventory

# 확인 생략
python manage.py seed_alpha_inventory --yes

# 특정 부서만
python manage.py seed_alpha_inventory --department skin
python manage.py seed_alpha_inventory --department treatment
python manage.py seed_alpha_inventory --department all

# 입고/출고 샘플 거래도 생성 (service 사용, [seed] 메모로 idempotent)
python manage.py seed_alpha_inventory --yes --with-transactions
```

특징:

```text
- idempotent: 여러 번 실행해도 중복 생성되지 않음(get_or_create + 초기재고 유일성 확인).
- 생성/재사용 건수 요약 출력.
- DEBUG=False 면 CommandError 로 즉시 중단.
- 테스트 계정 공통 비밀번호: test1234!
- 생성 계정: manager_test(MANAGER), skin_staff_test/skin_leader_test(피부실),
  treatment_staff_test/treatment_leader_test(치료실). superuser/ADMIN 은 만들지 않는다.
- 일부 품목은 일부러 "최소재고 이하"가 되도록 구성(부족 품목 화면 테스트용).
```

### 알파테스트 1회 세팅 흐름 (reset + seed)

```text
1) python manage.py reset_alpha_data --dry-run     # 무엇이 지워질지 확인
2) python manage.py reset_alpha_data               # 재고 데이터 초기화
3) python manage.py seed_alpha_inventory --dry-run # 무엇이 생길지 확인
4) python manage.py seed_alpha_inventory           # 샘플 데이터 생성
5) python manage.py runserver 0.0.0.0:8000         # (원내 LAN 테스트는 §1A)
6) STAFF/MANAGER 테스트 계정으로 로그인해 알파테스트
   - 예: skin_staff_test / manager_test  (비밀번호 test1234!)
```

> 위 명령들은 모두 **알파테스트용**이며 운영 데이터 세팅용이 아니다.

## 2. 관리자(ADMIN) 계정 생성 — 최소 2개

역할 변경과 ADMIN 권한 부여는 ADMIN 만 할 수 있다. ADMIN 이 1명뿐이고 접근이 막히면
운영 복구가 어려우므로 **활성 ADMIN 계정을 최소 2개** 둔다. (PRODUCT_SPEC §14.1)

```text
python manage.py createsuperuser
```

- `createsuperuser` 로 만든 계정은 자동으로 **role=ADMIN, is_staff=True, is_superuser=True** 가 된다.
- 위 명령을 **2회 이상** 실행해 ADMIN 을 2명 이상 만든다.
- ADMIN 은 `/admin/` (Django Admin)과 일반 운영 화면 모두 사용할 수 있다.

## 3. 부서 / 사용자 등록 (Django Admin)

ADMIN 으로 `/admin/` 에 로그인해 등록한다.

### 3.1 부서

```text
- 피부실(스킨앤라인) : is_active=True, active_for_inventory=True
- 치료실             : is_active=True, active_for_inventory=True
- (탕전실은 v0.1 재고관리 대상 아님: active_for_inventory=False)
```

### 3.2 사용자(직원 계정)

```text
- 직원별 개별 계정 생성 (공유 계정 사용 금지)
- 각 사용자에 역할(STAFF / TEAM_LEADER / MANAGER / ADMIN)과 부서 지정
- 승인 가능 계정(MANAGER 이상)을 최소 2개 둔다 (승인 병목 방지)
- 퇴사/비활성 직원은 삭제하지 않고 is_active=False 로 비활성화
```

**개인별 계정 원칙 (중요):**

```text
- 공유 계정(예: 치료실1, 데스크1) 사용을 금지한다.
- 이유: 입고/출고/취소/승인의 created_by / approved_by / canceled_by 추적성 유지.
- 직원은 본인 계정으로만 로그인한다.
```

**사용자 생성 후 비밀번호 설정 (필수):**

```text
- Django Admin 의 "사용자 추가" 화면에서 username + 비밀번호(2회 확인)를 입력해 생성한다.
  → 이 흐름을 따르면 비밀번호 없는 계정이 생기지 않는다.
- 생성 직후 "변경" 화면에서 이름/역할/부서를 지정한다.
- 비밀번호를 잊었거나 미설정인 계정은 다음으로 재설정한다:
    Admin 사용자 변경 화면의 비밀번호 변경 링크, 또는
    python manage.py changepassword <username>
```

**직원 비밀번호 변경 (셀프 서비스):**

```text
- 직원은 로그인 후 상단 네비게이션의 "비밀번호 변경"(/accounts/password-change/)에서
  본인 비밀번호를 직접 변경할 수 있다.
- 비활성(is_active=False) 사용자는 로그인할 수 없다.
```

역할 요약:

```text
STAFF        : 본인 부서 입고/출고/조회/실사조정 요청/초기재고 요청/당일 본인 거래 취소
TEAM_LEADER  : STAFF + 본인 부서 전체 거래 조회/당일 부서 거래 취소
MANAGER      : 전체 부서 조회·입력 + 승인/반려/취소 + 초기재고 즉시 승인
ADMIN        : 전체 + 사용자/역할 관리 + Django Admin
```

## 4. 마스터 데이터 등록 (Django Admin)

```text
1) 공급업체(Supplier) 등록
2) 품목 마스터(Item) 등록  — 분류는 고정 선택값, 구분 정보는 품목명에 포함 (예: 거즈 5x5)
3) 부서별 관리품목(ManagedItem) 등록 — Item + 부서 + 관리단위 + 최소재고 (+ 기본 공급업체)
```

> 주의: 관리단위(unit)는 운영 개시(승인 거래 발생) 후에는 변경할 수 없다.
> 단위를 바꿔야 하면 기존 관리품목을 비활성화하고 새로 만든다. (PRODUCT_SPEC §9.4)

## 5. 초기재고 입력 및 승인 (하드리셋 핵심)

온보딩 순서 (PRODUCT_SPEC §11.3):

```text
1. 부서 생성            (3.1)
2. 품목 마스터 생성      (4)
3. 부서별 관리품목 생성   (4)
4. 실제 재고 실사        (현장)
5. 초기재고(INITIAL_COUNT) 입력
6. MANAGER 또는 ADMIN 승인
7. 초기재고 승인 완료 확인
8. 입고/출고 운영 시작
```

- 직원(STAFF/TEAM_LEADER)이 입력한 초기재고는 **승인 대기(PENDING)** 상태다.
- MANAGER/ADMIN 이 입력하면 즉시 승인된다.
- 승인 대기 큐에서 **일괄 승인**으로 여러 초기재고를 한 번에 처리할 수 있다.
- **초기재고 승인 전에는 해당 품목의 입고/출고 운영을 시작하지 않는다.**
- 승인되지 않은 품목은 현재고가 0 으로 보일 수 있으므로 운영 시작 전 승인 여부를 반드시 확인한다.

## 6. 운영 시작 후 일상 사용 (요약)

```text
- 입고: 입고 등록 화면 (즉시 반영)
- 출고: 출고 등록 화면 (사용/폐기/분실/증정/기타출고 구분, 현재고 초과 불가)
- 현재고/최소재고 이하 품목: 조회 화면
- 재고 불일치: 실사조정 요청 → MANAGER 승인
- 오입력: 삭제가 아니라 "취소"로 처리 (당일 본인/부서 거래 또는 MANAGER 이상)
```

팀장 외 1명 이상이 위 업무(입고/출고/조회/실사조정 요청/오입력 취소)를 익혀
특정 개인에게 지식이 묶이지 않게 한다. (PRODUCT_SPEC §11.5)

## 7. 비상 ADMIN 복구 절차 (운영진 전용 · 일반 직원 비공개)

ADMIN 계정 전부에 접근할 수 없게 된 경우의 복구 절차다. **서버 접근 권한이 있는
담당자만** 수행하며, 절차/계정 정보는 일반 직원에게 공유하지 않는다. (PRODUCT_SPEC §14.1)

```text
1) 운영 서버에 접속한다 (셸/배포 권한 필요).
2) 프로젝트 디렉터리에서 가상환경을 활성화하고 환경변수(.env)가 로드되는지 확인한다.
3) 비상 ADMIN 계정을 새로 생성한다:
     python manage.py createsuperuser
   (생성된 계정은 자동으로 role=ADMIN / is_staff=True / is_superuser=True)
4) 새 ADMIN 으로 /admin/ 에 로그인해 기존 계정 상태를 점검한다.
5) 필요 시 기존 사용자 비밀번호 초기화 / 역할 재지정:
     python manage.py changepassword <username>
6) 복구 후, 활성 ADMIN 이 다시 2개 이상인지 확인한다.
```

운영 원칙:

```text
- 활성 ADMIN 계정은 항상 최소 2개 유지한다.
- 비상 복구 절차와 계정 정보는 운영진 문서에서만 관리하고 일반 직원에게 공유하지 않는다.
- DB 접속정보·비밀번호는 코드에 저장하지 않고 환경변수로 관리한다.
```

## 8. 운영 투입 최종 절차

```text
1) 자동 테스트가 PostgreSQL 에서 전부 통과하는지 확인 (개발/배포 담당, README 참조)
2) MANUAL_QA_CHECKLIST.md 의 1~10 섹션을 점검
3) 활성 ADMIN 2개 이상 / 승인 가능 MANAGER 이상 2개 이상 확인
4) 적용 파트(피부실 또는 치료실)의 관리품목·초기재고 등록 및 승인 완료 확인
5) 팀장 외 1명 이상 교육 완료 확인
6) 최소 1주일 입고/출고/폐기 기록 운영 → 운영진이 최소재고 이하 품목을 데이터로 확인
```

위가 충족되면 기존 AppSheet/Google Sheets 병행 없이 새 시스템으로 재고 흐름을 운영한다.
