# gimpo365-inventory v0.1 TASKS.md v1.2

문서 상태: 구현 지시용 2차 보완본  
대상: Codex / Claude Code 작업 지시용  
전제 문서: PRODUCT_SPEC.md, TECH_SPEC.md  
중요: 이 문서는 TECH_SPEC 확정본을 기준으로 작성한다.

---

## 0. 최상위 지시문

이 프로젝트는 김포365한의원 내부 재고관리 시스템 `gimpo365-inventory v0.1`이다.

구현자는 반드시 `TECH_SPEC.md`를 기준으로 작업한다.

아래 금지사항을 위반하지 않는다.

```text
AUTH_USER_MODEL 설정 전 migrate 실행 금지
Django 기본 User로 첫 migration 생성 금지
SQLite로 테스트 실행 금지
SQLite에서 통과한 테스트를 완료 기준으로 인정 금지

StockTransaction 생성·상태 변경은 반드시 inventory/services.py를 통해서만 수행
View, Form, Admin에서 StockTransaction.objects.create() 직접 호출 금지
View, Form, Admin에서 transaction.status 직접 변경 후 save() 금지

Django Admin에서 StockTransaction add/delete 금지
Django Admin에서 StockTransaction managed_item/status/quantity 필드 수정 금지

Profile 모델 생성 금지
Item name + specification unique 구현 금지
Inventory Manager 그룹 v0.1 구현 금지
get_current_stock_for_update selector 생성 금지
```

예외:

```text
테스트 fixture/factory에서는 제약조건 검증 목적상 StockTransaction을 직접 생성할 수 있다.
단, application code에서는 StockTransaction 직접 생성/상태변경을 금지한다.
```

---

## 1. 확정 사실

```text
Backend: Django
DB: PostgreSQL
Frontend: Django Template
Admin: Django Admin
Auth: Django 기본 인증
Custom User: accounts.User(AbstractUser)
AUTH_USER_MODEL = "accounts.User"
Department 위치: core.Department
재고 현재고: StockTransaction APPROVED quantity_delta 합계
Django Admin: v0.1에서는 ADMIN 전용
Inventory Manager 그룹: v0.1 미구현, v0.2 위임 후보
테스트 DB: PostgreSQL
```

---

## 2. 폐기된 결정

아래는 구현하지 않는다.

```text
Django 기본 User + Profile 방식
inventory.Department 배치
Item name + specification unique
Inventory Manager 그룹 v0.1 구현
SQLite 테스트
get_current_stock_for_update selector
StockTransaction Admin add 허용
Generic CreateView/UpdateView에서 ModelForm.save()로 StockTransaction 직접 저장
View/Form/Admin에서 StockTransaction 직접 create/save
```

---

## 3. 작업 순서 개요

진행 상태: **TASK 00 ~ 21 전부 완료.** 자동 테스트 147건 PostgreSQL 통과.
(상태 표기는 v0.1 구현 완료 시점 기준)

```text
[x] TASK 00. 구현 전 전역 규칙 확인
[x] TASK 01. 프로젝트 초기 설정
[x] TASK 02. core.Department + accounts.User + AUTH_USER_MODEL
[x] TASK 03. PostgreSQL 테스트 환경 / 기본 fixture
[x] TASK 04. inventory 마스터 모델: Supplier / Item / ManagedItem
[x] TASK 05. StockTransaction 모델 / DB 제약조건
[x] TASK 06. selector 함수
[x] TASK 07. permission / exception
[x] TASK 08. service 공통 구조
[x] TASK 09. 입고 / 출고 service
[x] TASK 10. 초기재고 / 실사조정 service
[x] TASK 11. 승인 / 반려 / 철회 service
[x] TASK 12. 취소 / 일괄 승인 service
[x] TASK 13. Form 구현
[x] TASK 14. 기본 layout / login / dashboard
[x] TASK 15. 조회 화면
[x] TASK 16. 생성 화면
[x] TASK 17. 승인 / 취소 상태 변경 화면
[x] TASK 18. Django Admin 설정
[x] TASK 19. 전체 테스트 / 회귀 테스트 보강
[x] TASK 20. 수동 점검 체크리스트 (MANUAL_QA_CHECKLIST.md)
[x] TASK 21. 문서 정리 (README / OPERATIONS_SETUP)
```

---

# TASK 00. 구현 전 전역 규칙 확인

## 목표

구현자가 반드시 지켜야 할 전역 규칙을 확인한다.

## 작업

```text
1. PRODUCT_SPEC.md 확인
2. TECH_SPEC.md 확인
3. TASKS.md 확인
4. 폐기된 결정 확인
5. 절대 금지사항 확인
```

## 완료 기준

```text
구현자는 아래 규칙을 명확히 이해해야 한다.

- Custom User 첫 migration 규칙
- PostgreSQL 테스트 원칙
- StockTransaction 직접 create/save 금지
- service 함수 중심 변경 원칙
- Admin 거래 원장 add/delete 금지
```

---

# TASK 01. 프로젝트 초기 설정

## 목표

Django 프로젝트 기본 구조를 만든다.

## 작업

```text
1. Django 프로젝트 생성
2. config 앱 설정
3. core / accounts / inventory 앱 생성
4. PostgreSQL 연결 설정
5. .env.example 작성
6. requirements.txt 작성
7. 기본 template/static 설정
8. README.md 초기 작성
```

## 완료 기준

```text
Django 프로젝트가 실행된다.
PostgreSQL 설정이 준비된다.
아직 migrate를 실행하지 않는다.
```

## 금지

```text
아직 migrate 실행 금지
AUTH_USER_MODEL 설정 전 migrate 금지
Django 기본 User로 첫 migration 생성 금지
```

---

# TASK 02. core.Department + accounts.User + AUTH_USER_MODEL

## 목표

첫 migration 전에 Department와 Custom User를 함께 확정한다.

이 TASK는 매우 중요하다.

`accounts.User.department`가 `core.Department`를 참조하므로, `Department`와 `Custom User`는 첫 migration 전에 함께 준비한다.

## 작업

```text
1. core.Department 모델 작성
2. Department.name unique 설정
3. Department.is_active 설정
4. Department.active_for_inventory 설정
5. Department.name strip 정규화 구현

6. accounts.User(AbstractUser) 모델 작성
7. Role choices 작성
8. User.name 필드 추가
9. User.department = ForeignKey(core.Department, null=True, blank=True, on_delete=SET_NULL)
10. User.role 기본값 STAFF
11. User.created_at / updated_at 추가
12. User.REQUIRED_FIELDS = [] 설정
13. UserManager 작성
14. create_superuser()에서 role=ADMIN, is_staff=True, is_superuser=True 강제
15. settings.AUTH_USER_MODEL = "accounts.User" 설정
16. accounts.permissions.py 기본 역할 헬퍼 작성
17. makemigrations 실행
18. migrate 실행
```

## 완료 기준 테스트

```text
3.1 AUTH_USER_MODEL 설정 테스트
3.2 REQUIRED_FIELDS 테스트
3.3 create_superuser 기본값 테스트
3.4 일반 사용자 기본 role 테스트
4.1 Department.name unique 테스트
4.11 Department.name strip 정규화 테스트
accounts.permissions role helper 단위 테스트
- STAFF < TEAM_LEADER < MANAGER < ADMIN 순서 확인
- has_role_at_least(user, role) 동작 확인
- is_manager_or_above(user) 동작 확인
- is_admin_role(user) 동작 확인
```

## 금지

```text
Profile 모델 생성 금지
AUTH_USER_MODEL 설정 전 migrate 금지
Django 기본 User로 첫 migration 생성 금지
```
## 참고

`accounts.User.department`가 `core.Department`를 참조하므로 일반적으로 TASK 02의 한 번의 흐름으로 정상 migration이 가능하다.

만약 migration 순환 의존 오류가 발생하면 다음 방식으로 해결한다.

```text
1. User 최초 migration에서는 department FK를 임시로 제외
2. AUTH_USER_MODEL 설정 후 첫 migration 실행
3. 후속 migration에서 User.department FK 추가
```

단, 이 우회는 실제 오류가 발생한 경우에만 사용한다.


---

# TASK 03. PostgreSQL 테스트 환경 / 기본 fixture

## 목표

앞으로의 모든 작업을 PostgreSQL 테스트 환경에서 검증할 수 있게 한다.

## 작업

```text
1. 테스트 설정 작성
2. PostgreSQL 테스트 DB 사용 확인
3. SQLite 테스트 방지
4. pytest 또는 Django TestCase 구조 설정
5. 공통 fixture 또는 factory 작성
6. 기본 부서 fixture 작성
7. 기본 사용자 fixture 작성
```

## 기본 테스트 데이터

```text
부서:
- 피부실: active_for_inventory=True
- 치료실: active_for_inventory=True
- 탕전실: active_for_inventory=False

사용자:
- staff_skin: STAFF, 피부실
- team_leader_skin: TEAM_LEADER, 피부실
- staff_treatment: STAFF, 치료실
- manager: MANAGER, is_staff=False, is_superuser=False
- admin: ADMIN, is_staff=True, is_superuser=True
```

## 완료 기준

```text
PostgreSQL에서 테스트 실행 가능
SQLite로 테스트가 실행되지 않음
Department/User fixture 사용 가능
Supplier/Item/ManagedItem fixture는 해당 모델 구현 후 TASK 04에서 확장
```

## 완료 기준 테스트

```text
PostgreSQL 테스트 DB 확인
기본 fixture 생성 확인
```

## 금지

```text
SQLite에서 통과한 테스트를 완료로 인정 금지
```

---

# TASK 04. inventory 마스터 모델: Supplier / Item / ManagedItem

## 목표

재고 마스터 데이터를 구현한다.

## 작업

```text
1. Supplier 모델 구현
2. Supplier.name unique
3. Supplier.name strip 정규화
4. Supplier.is_active

5. Item 모델 구현
6. Item.name unique
7. Item.name strip 정규화
8. Item.category choices
9. Item.category default 없음
10. Item.specification은 설명용

11. ManagedItem 모델 구현
12. ManagedItem.item = PROTECT
13. ManagedItem.department = PROTECT
14. ManagedItem.default_supplier = PROTECT
15. ManagedItem.unit choices
16. ManagedItem.minimum_stock DecimalField
17. ManagedItem(department, item) unique
18. ManagedItem.is_active
19. Supplier / Item / ManagedItem fixture 확장
20. makemigrations 실행
21. migrate 실행
```

## 완료 기준 테스트

```text
4.2 Supplier.name unique 테스트
4.3 Item.name unique 테스트
4.4 Item.specification은 unique 기준이 아님
4.5 ManagedItem department + item unique 테스트
4.6 다른 부서의 같은 Item 허용 테스트
4.11 Supplier/Item name strip 정규화 테스트
Supplier / Item / ManagedItem fixture 생성 확인
```

## 후속 테스트로 미룸

아래 테스트는 StockTransaction 모델 구현 후 진행한다.

```text
5.1 APPROVED 거래가 없으면 unit 변경 가능
5.2 APPROVED 거래가 있으면 unit 변경 불가
5.3 PENDING 거래만 있으면 unit 변경 가능
PostgreSQL DB에 partial unique index / CheckConstraint / index 적용 확인
```

## 금지

```text
Item name + specification unique 구현 금지
마스터 데이터 삭제 중심 구현 금지
```

---

# TASK 05. StockTransaction 모델 / DB 제약조건

## 목표

재고 거래 원장 모델과 DB 제약조건을 구현한다.

## 작업

```text
1. StockTransaction 모델 구현
2. TransactionType choices
3. TransactionStatus choices
4. quantity_input DecimalField
5. quantity_delta DecimalField
6. expected_quantity DecimalField null=True blank=True
7. actual_quantity DecimalField null=True blank=True
8. occurred_at = timezone.now
9. created_by / approved_by / canceled_by related_name 설정
10. supplier / unit_price / expiration_date
11. reason / review_note / memo / cancel_reason
12. APPROVED INITIAL_COUNT partial unique index 구현
13. quantity_input >= 0 CheckConstraint
14. expected_quantity >= 0 또는 null CheckConstraint
15. actual_quantity >= 0 또는 null CheckConstraint
16. unit_price >= 0 또는 null CheckConstraint
17. StockTransaction(managed_item, status) 인덱스 구현
18. ManagedItem.unit 변경 금지 clean() 구현
19. StockTransaction fixture/factory 확장
20. makemigrations 실행
21. migrate 실행
```

## 완료 기준 테스트

```text
4.7 APPROVED INITIAL_COUNT 유일성 테스트
4.8 PENDING INITIAL_COUNT 중복 허용 테스트
4.9 quantity_input 음수 차단 테스트
4.10 quantity_delta 음수 허용 테스트
5.1 APPROVED 거래가 없으면 unit 변경 가능
5.2 APPROVED 거래가 있으면 unit 변경 불가
5.3 PENDING 거래만 있으면 unit 변경 가능
```

## 금지

```text
quantity_delta >= 0 제약조건 구현 금지
StockTransaction CASCADE FK 금지
```

---

# TASK 06. selector 함수

## 목표

조회 전용 로직을 구현한다.

## 작업

```text
1. inventory/selectors.py 생성
2. get_current_stock()
3. get_accessible_managed_items()
4. get_managed_items_with_current_stock()
5. get_low_stock_managed_items()
6. get_transactions()
7. get_pending_transactions()
8. has_approved_initial_count()
```

## 완료 기준 테스트

```text
6.1 get_current_stock 기본 테스트
6.2 PENDING 거래 제외 테스트
6.3 REJECTED 거래 제외 테스트
6.4 CANCELED 거래 제외 테스트
6.5 거래가 없으면 0 반환
6.6 get_accessible_managed_items STAFF 범위 테스트
6.7 get_accessible_managed_items MANAGER 범위 테스트
6.8 active_for_inventory=False 부서 제외 테스트
6.9 최소재고 이하 품목 조회 테스트
6.10 최소재고 초과 품목 제외 테스트
```

## 금지

```text
get_current_stock_for_update 생성 금지
selector에서 select_for_update 사용 금지
selector에서 데이터 변경 금지
```

---

# TASK 07. permission / exception

## 목표

권한과 예외 클래스를 분리한다.

## 작업

```text
1. inventory/exceptions.py 생성
2. InventoryError
3. PermissionDeniedError
4. InvalidTransactionStateError
5. InsufficientStockError
6. DuplicateInitialCountError
7. InvalidQuantityError
8. InvalidManagedItemError
9. inventory/permissions.py 생성
10. can_access_managed_item()
11. can_cancel_transaction()
```

## 완료 기준 테스트

TASK 07은 service 함수가 아직 구현되기 전 단계다.

따라서 완료 기준은 service 호출 테스트가 아니라 permission 함수 자체의 단위 테스트로 둔다.

```text
can_access_managed_item(staff_skin, 피부실 ManagedItem) == True
can_access_managed_item(staff_skin, 치료실 ManagedItem) == False
can_access_managed_item(team_leader_skin, 피부실 ManagedItem) == True
can_access_managed_item(manager, 피부실 ManagedItem) == True
can_access_managed_item(manager, 치료실 ManagedItem) == True

can_cancel_transaction(staff_skin, 본인이 당일 등록한 APPROVED IN 거래) == True
can_cancel_transaction(staff_skin, 타인이 등록한 APPROVED IN 거래) == False
can_cancel_transaction(staff_skin, 전일 APPROVED IN 거래) == False
can_cancel_transaction(team_leader_skin, 본인 부서 당일 APPROVED 일반 거래) == True
can_cancel_transaction(team_leader_skin, 타 부서 APPROVED 일반 거래) == False
can_cancel_transaction(manager, 전체 부서 APPROVED 일반 거래) == True
can_cancel_transaction(admin, 전체 부서 APPROVED 일반 거래) == True
can_cancel_transaction(user, APPROVED INITIAL_COUNT) == False
can_cancel_transaction(user, APPROVED ADJUSTMENT) == False
can_cancel_transaction(user, PENDING 거래) == False
can_cancel_transaction(user, REJECTED 거래) == False
can_cancel_transaction(user, CANCELED 거래) == False
```

service 권한 테스트인 11.x / 12.x는 TASK 11 / TASK 12 완료 기준에서만 검증한다.
```

---

# TASK 08. service 공통 구조

## 목표

service 함수 구현에 필요한 공통 구조를 준비한다.

## 작업

```text
1. inventory/services.py 생성
2. 공통 수량 검증 함수 작성
3. 공통 occurred_at 미래 날짜 검증 작성
4. 공통 managed_item 접근 검증 작성
5. 공통 row lock 패턴 정리
6. 공통 status 재확인 패턴 정리
7. service 함수에서 사용할 내부 helper 작성
```

## 완료 기준

```text
service 함수에서 공통 검증을 재사용할 준비가 되어 있다.
application code에서 StockTransaction 직접 create/save를 쓰지 않는 원칙이 문서화되어 있다.
```

## 금지

```text
View/Form/Admin에 원장 변경 로직 작성 금지
```

---

# TASK 09. 입고 / 출고 service

## 목표

입고와 출고 service를 구현한다.

## 작업

```text
1. create_stock_in()
2. create_stock_out()
3. 입고 quantity > 0 검증
4. 출고 quantity > 0 검증
5. 출고 transaction_type OUT 계열 검증
6. 출고 현재고 음수 방지
7. create_stock_out에서 ManagedItem row lock
8. created_by 기록
9. supplier 기본값 처리
```

## 완료 기준 테스트

```text
7.1 create_stock_in 성공 테스트
7.2 create_stock_in 타 부서 차단 테스트
7.3 create_stock_in quantity 0 차단 테스트
7.4 create_stock_in 음수 차단 테스트
7.6 supplier 기본값 테스트
8.1 create_stock_out 성공 테스트
8.2 현재고 초과 출고 차단 테스트
8.3 현재고와 같은 수량 출고 허용 테스트
8.4 OUT 계열 외 transaction_type 차단 테스트
8.5 타 부서 출고 차단 테스트
created_by 기록 테스트
```

## 주의

```text
STAFF unit_price 제한은 Form에서 처리한다.
service 테스트에서 STAFF unit_price 차단/무시 기대값을 모호하게 두지 않는다.
```

---

# TASK 10. 초기재고 / 실사조정 service

## 목표

초기재고와 실사조정 요청 service를 구현한다.

## 작업

```text
1. request_adjustment()
2. request_initial_count()
3. adjustment reason 필수
4. actual_quantity >= 0 검증
5. expected_quantity 기록
6. quantity_delta = actual_quantity - expected_quantity
7. STAFF/TL 초기재고는 PENDING
8. MANAGER/ADMIN 초기재고는 APPROVED
9. APPROVED INITIAL_COUNT 존재 시 추가 요청 차단
10. PENDING INITIAL_COUNT 중복 요청 허용
```

## 완료 기준 테스트

```text
9.1 request_adjustment 성공 테스트
9.2 adjustment reason 필수 테스트
9.3 actual_quantity 음수 차단 테스트
10.1 STAFF 초기재고 요청 테스트
10.2 MANAGER 초기재고 즉시 승인 테스트
10.3 이미 승인된 초기재고가 있으면 요청 차단
10.4 PENDING 초기재고 중복 요청 허용
실사조정 delta 정합성 테스트
```

---

# TASK 11. 승인 / 반려 / 철회 service

## 목표

PENDING 거래 승인, 반려, 철회 service를 구현한다.

## 작업

```text
1. approve_transaction()
2. reject_transaction()
3. withdraw_pending_transaction()
4. approve 권한 MANAGER 이상
5. reject 권한 MANAGER 이상
6. withdraw 권한 생성자 또는 MANAGER 이상
7. StockTransaction select_for_update
8. status 재확인
9. INITIAL_COUNT 승인 시 중복 차단
10. ADJUSTMENT 승인 시 현재고 음수 방지
11. reject review_note 필수
12. withdraw cancel_reason 필수
13. approved_by / approved_at 기록
14. canceled_by / canceled_at 기록
```

## 완료 기준 테스트

```text
9.4 adjustment 승인 성공 테스트
9.5 adjustment 승인 시 현재고 음수 차단 테스트
9.6 adjustment 반려 테스트
9.7 adjustment 철회 테스트
10.5 초기재고 승인 성공 테스트
10.6 초기재고 승인 시 중복 차단 테스트
10.7 초기재고 반려 테스트
10.8 초기재고 철회 테스트
11.1 APPROVE 권한 테스트
11.2 MANAGER 승인 가능 테스트
11.3 REJECT 권한 테스트
11.4 REJECT review_note 필수 테스트
11.5 CANCELED 거래 재승인 차단 테스트
11.6 REJECTED 거래 재승인 차단 테스트
11.7 PENDING 철회 생성자 가능 테스트
11.8 PENDING 철회 타인 차단 테스트
approved_by / approved_at 기록 테스트
rejected 거래의 approved_by / approved_at 기록 테스트
canceled_by / canceled_at 기록 테스트
```

---

# TASK 12. 취소 / 일괄 승인 service

## 목표

APPROVED 일반 거래 취소와 초기재고 일괄 승인 service를 구현한다.

## 작업

```text
1. cancel_transaction()
2. bulk_approve_initial_counts()
3. APPROVED 일반 거래만 취소 허용
4. INITIAL_COUNT / ADJUSTMENT 취소 차단
5. 취소 후 현재고 음수 방지
6. cancel_reason 필수
7. canceled_by / canceled_at 기록
8. bulk approve 대상은 PENDING INITIAL_COUNT
9. bulk approve 거래별 savepoint
10. 한 건 실패 시 전체 롤백 방지
11. skipped 목록 반환
```

## 완료 기준 테스트

```text
12.1 STAFF 당일 본인 거래 취소 가능
12.2 STAFF 타인 거래 취소 차단
12.3 STAFF 전일 거래 취소 차단
12.4 TEAM_LEADER 본인 부서 당일 거래 취소 가능
12.5 TEAM_LEADER 타 부서 거래 취소 차단
12.6 MANAGER 전체 거래 취소 가능
12.7 취소 후 현재고 음수 차단 테스트
12.8 OUT 거래 취소 성공 테스트
12.9 INITIAL_COUNT 취소 차단 테스트
12.10 ADJUSTMENT 취소 차단 테스트
13.1 초기재고 일괄 승인 성공 테스트
13.2 일부 실패 부분 성공 테스트
13.3 한 건 실패가 전체 롤백하지 않는지 테스트
13.4 bulk approve 권한 테스트
13.5 ADJUSTMENT는 bulk approve 대상 제외
canceled_by / canceled_at 기록 테스트
```

---

# TASK 13. Form 구현

## 목표

user-aware Form을 구현한다.

## 작업

```text
1. inventory/forms.py 생성
2. StockFilterForm
3. TransactionFilterForm
4. PendingTransactionFilterForm
5. StockInForm
6. StockOutForm
7. AdjustmentRequestForm
8. InitialCountForm
9. ApproveTransactionForm
10. RejectTransactionForm
11. WithdrawPendingTransactionForm
12. CancelTransactionForm
13. BulkApproveInitialCountsForm
14. 생성 Form __init__(user=...) 구현
15. managed_item queryset = get_accessible_managed_items(user)
16. STAFF StockInForm에서 unit_price 필드 제거
17. TEAM_LEADER 이상 StockInForm에는 unit_price 필드 표시
18. occurred_at 기본값 timezone.now
19. occurred_at 미래 날짜 차단
20. reject review_note 필수
21. withdraw/cancel cancel_reason 필수
```

## 완료 기준 테스트

```text
14.1 StockInForm user-aware queryset 테스트
14.2 StockOutForm user-aware queryset 테스트
14.3 AdjustmentRequestForm user-aware queryset 테스트
14.4 InitialCountForm user-aware queryset 테스트
14.5 STAFF StockInForm unit_price 제거 테스트
14.6 TEAM_LEADER StockInForm unit_price 표시 테스트
14.7 occurred_at 기본값 테스트
14.8 occurred_at 미래 날짜 차단 테스트
```

---

# TASK 14. 기본 layout / login / dashboard

## 목표

기본 화면 구조와 로그인 흐름을 구현한다.

## 작업

```text
1. base.html
2. navbar.html
3. messages.html
4. accounts/login.html
5. LoginView / LogoutView 설정
6. HomeRedirectView
7. InventoryDashboardView
8. Admin 버튼 표시 조건 user.is_staff
9. role 표시
10. Django messages framework 적용
```

## 완료 기준 테스트

```text
15.1 비로그인 사용자는 inventory 화면 접근 불가
16.8 Admin 버튼 표시 테스트
```

---

# TASK 15. 조회 화면

## 목표

현재고, 최소재고 이하, 거래 이력 조회 화면을 구현한다.

## 작업

```text
1. StockListView
2. LowStockListView
3. TransactionListView
4. StockFilterForm 연결
5. TransactionFilterForm 연결
6. selector 함수 사용
7. 거래 취소 버튼 표시 조건 can_cancel_transaction 사용
8. INITIAL_COUNT / ADJUSTMENT 취소 버튼 없음
```

## 완료 기준 테스트

```text
18.1 승인된 INITIAL_COUNT 취소 버튼 없음
18.2 승인된 ADJUSTMENT 취소 버튼 없음
```

## 수동 체크

```text
현재고 목록 표시
최소재고 이하 표시
거래 이력 필터 동작
초기재고/실사조정 보정 안내 문구 표시
```

---

# TASK 16. 생성 화면

## 목표

입고, 출고, 실사조정, 초기재고 입력 화면을 구현한다.

## 작업

```text
1. StockInCreateView
2. StockOutCreateView
3. AdjustmentRequestView
4. InitialCountRequestView
5. 모든 View에서 user-aware Form 사용
6. form.cleaned_data를 service 함수에 전달
7. ModelForm.save()로 StockTransaction 직접 저장 금지
8. 성공 후 같은 Form에 머무름
9. 성공 메시지 표시
10. 실패 시 service 예외 메시지 표시
```

## 완료 기준 테스트

```text
15.9 입고 등록 후 같은 Form에 머무름
15.10 출고 등록 후 같은 Form에 머무름
```

## 금지

```text
StockTransaction.objects.create() 직접 호출 금지
ModelForm.save()로 StockTransaction 저장 금지
```

---

# TASK 17. 승인 / 취소 상태 변경 화면

## 목표

승인, 반려, 철회, 취소, 일괄 승인 화면을 구현한다.

## 작업

```text
1. PendingTransactionListView
2. ApproveTransactionView
3. RejectTransactionView
4. WithdrawPendingTransactionView
5. CancelTransactionView
6. BulkApproveInitialCountsView
7. 모든 상태 변경은 POST에서만 수행
8. GET은 확인 Form만 렌더링
9. CSRF 적용
10. View GET/POST 양쪽에서 권한 재검사
11. service 함수 호출
12. 승인 큐에서 INITIAL_COUNT 체크박스 제공
13. 선택 항목 일괄 승인 버튼 구현
14. bulk approve 결과 표시
```

## 완료 기준 테스트

```text
15.2 STAFF는 pending 화면 접근 불가
15.3 MANAGER는 pending 화면 접근 가능
15.4 cancel URL 직접 접근 차단
15.5 approve URL 직접 접근 차단
15.6 GET은 상태 변경하지 않음
15.7 POST만 상태 변경 수행
15.8 CSRF 없는 POST 차단
```

## 금지

```text
GET 요청에서 상태 변경 금지
상태 변경을 링크 클릭만으로 처리 금지
```

---

# TASK 18. Django Admin 설정

## 목표

Admin을 ADMIN 전용 관리 도구로 설정한다.

## 작업

```text
1. UserAdmin 설정
2. DepartmentAdmin 설정
3. SupplierAdmin 설정
4. ItemAdmin 설정
5. ManagedItemAdmin 설정
6. StockTransactionAdmin 설정
7. StockTransaction has_add_permission=False
8. StockTransaction has_delete_permission=False
9. StockTransaction readonly_fields 설정
10. managed_item readonly 포함
11. status readonly 포함
12. quantity_input / quantity_delta readonly 포함
13. created_by / approved_by / canceled_by readonly 포함
14. ManagedItem unit 수정 제한 반영
15. Inventory Manager 그룹 미구현
```

## 완료 기준 테스트

```text
16.1 일반 STAFF Admin 접근 불가
16.2 MANAGER 기본 Admin 접근 불가
16.3 ADMIN Admin 접근 가능
16.4 StockTransaction Admin add 차단
16.5 StockTransaction Admin delete 차단
16.6 StockTransaction Admin readonly 필드 테스트
16.7 User Admin은 ADMIN 전용
16.8 Admin 버튼 표시 테스트
```

---

# TASK 19. 전체 테스트 / 회귀 테스트 보강

## 목표

누락된 테스트를 보강하고 전체 P0 테스트를 PostgreSQL에서 실행한다.

## 작업

```text
1. P0 테스트 전체 실행
2. P1 테스트 가능한 범위 실행
3. PostgreSQL에서 실행되는지 확인
4. SQLite 미사용 확인
5. Admin 테스트 자동화 확인
6. bulk approve 부분 성공 테스트 확인
7. 감사 필드 테스트 확인
8. 실사조정 delta 정합성 테스트 확인
9. flaky 동시성 테스트는 자동화하지 않고 수동/통합 검증으로 분리
10. 17.4 동시 INITIAL_COUNT 승인 중복 방지의 결정적 보장은 4.7 / 10.6 자동 테스트로 커버
11. 실제 타이밍 기반 동시성 경합은 TASK 20 수동/통합 검증으로 분리
```

## 완료 기준

```text
P0 테스트 전체 통과
PostgreSQL에서 테스트 통과
SQLite 테스트 결과 사용 안 함
```

---

# TASK 20. 수동 점검 체크리스트

## 목표

자동화하지 않는 항목을 운영 투입 전 수동 점검한다.

## 체크 항목

```text
화면 카피
초기재고/실사조정 보정 안내 문구
성공/실패 메시지
연속 입력 UX
관리자 계정 2개 이상 존재
실제 피부실/치료실 부서 생성
기본 품목/관리품목 등록 흐름
모바일 브라우저 기본 사용성
동시 출고 수동/통합 검증
approve/reject 동시 처리 수동/통합 검증
approve/withdraw 동시 처리 수동/통합 검증
동시 INITIAL_COUNT 승인 타이밍 경합 수동/통합 검증
```

---

# TASK 21. 문서 정리

## 목표

구현 완료 후 문서를 정리한다.

## 작업

```text
1. README.md 업데이트
2. PRODUCT_SPEC.md 보관
3. TECH_SPEC.md 최신화
4. TASKS.md 체크 상태 업데이트
5. 운영자 초기 설정 가이드 작성
6. 테스트 실행 방법 작성
7. PostgreSQL 테스트 실행 방법 명시
8. 비상 ADMIN 계정 복구 절차 기록
```

---

## 4. 출시 게이트

v0.1 운영 투입 전 반드시 충족해야 한다.

```text
P0 테스트 전체 통과
PostgreSQL에서 테스트 통과
ADMIN 계정 최소 2개 준비
StockTransaction Admin add/delete 차단 확인
입고/출고/취소/초기재고/실사조정 주요 흐름 수동 점검
SQLite 테스트 미사용 확인
```

---

## 5. 구현자 주의사항

```text
편의를 위해 ModelForm.save()로 StockTransaction을 직접 저장하지 마라.
Generic CreateView/UpdateView를 사용할 경우에도 form_valid에서 service 함수만 호출하라.
상태 변경 링크를 GET으로 처리하지 마라.
모든 상태 변경은 POST + CSRF로 처리하라.
Form에는 user를 전달하라.
STAFF에게 타 부서 ManagedItem을 노출하지 마라.
StockTransaction Admin에서 managed_item을 수정 가능하게 두지 마라.
StockTransaction Admin에서 add/delete를 허용하지 마라.
```

---

## 6. v0.1.1 사용성 개선 (적용 완료)

운영 수동 사용 중 발견한 입력 UX 개선. 재고 원장/서비스 원칙·테스트 불변.

```text
- 입고등록 occurred_at → "입고일자"(날짜 선택), 내부 datetime 변환(오늘=현재시각/과거=00:00), 미래 금지
- 입고등록 유통기한 → HTML date input(달력)
- 수량 input step=1 (DecimalField 유지, 소수 직접 입력 가능)
- 관리품목 선택지 라벨에 규격(specification)/부서/단위 노출, 출고는 현재고 추가 표시
- 실사조정 사유 → 고정 선택값 드롭다운("기타"는 메모 안내)
- 관리품목 검색 필터(외부 라이브러리 없음, user-aware 옵션만 필터)
- 계정: 개인별 계정 원칙/공유 금지/비활성화 운영 문서화, 직원 비밀번호 변경 화면(/accounts/password-change/)
- 권한: 실사조정/최초 재고 입력 요청은 TEAM_LEADER 이상(STAFF 차단). 승인/반려는 MANAGER 이상 유지
- 흐름: 별도 '초기재고 입력' 화면 제거 → '실사조정 요청'으로 통합.
  선택 품목에 승인된 최초 재고가 없으면 INITIAL_COUNT(최초 재고 입력), 있으면 ADJUSTMENT(실사조정)로 자동 분기.
  내부 거래유형(INITIAL_COUNT/ADJUSTMENT)과 service/유일성/현재고 계산 원칙은 그대로 유지.
```

## 7. v0.2 후보 (설계 메모, 미구현)

### 7.0 StorageLocation 모델화 (v0.1.1 보류)

알파테스트에서 "관리품목 storage_location 을 드롭다운으로 관리" 요청. v0.1.1 에서는
모델 신설 없이 **기존 입력값 기반 datalist 자동완성(Admin)** 으로 최소 대응했다.
별도 `StorageLocation` 모델 + ManagedItem FK 전환은 v0.2 설계 후보로 둔다.
(이번 단계에서 모델/마이그레이션 변경 금지)


### 7.1 로그인 실패 잠금 (인증 로직 변경 — 별도 TASK 로 분리)

이번 v0.1.1 에서는 구현하지 않고 설계 후보로만 기록한다. 인증 흐름에 영향을 주므로
별도 TASK 로 분리해 구현한다.

```text
정책 초안:
- 로그인 실패 5회 시 15분 임시 잠금
- ADMIN 은 잠금 해제 가능
- 실패 횟수와 잠금 시각(마지막 실패 시각)을 기록
- 잠금 상태에서는 로그인 차단 + 안내 메시지 표시
- 퇴사자는 is_active=False 로 차단 (기존 정책 유지)

구현 고려:
- 실패 카운트/잠금 시각 저장 위치 (User 확장 필드 또는 별도 모델)
- 인증 백엔드 또는 LoginView 커스터마이즈 지점
- 잠금 해제 UI(ADMIN) 및 감사 로그
- 타이밍/동시성: 카운트 증가 경합 처리
```
