# gimpo365-inventory v0.1 TECH_SPEC 확정본

문서 상태: v0.1 구현 기준 확정본  
작성 목적: Codex / Claude Code 구현 기준 단일 문서  
주의: 기존 초안의 폐기된 내용을 제거하고 최종 결정만 병합한 문서다.

---

## 0. 목적

김포365한의원 내부 재고관리 시스템 `gimpo365-inventory v0.1`의 기술 구현 기준을 정의한다.

핵심 목표:

```text
1. PRODUCT_SPEC을 Django + PostgreSQL 구현 구조로 변환한다.
2. 모델, 권한, 서비스 함수, 화면 구조, 테스트 기준을 확정한다.
3. Codex / Claude Code가 옛 결정을 참조하지 않도록 단일 기준을 제공한다.
4. 재고 원장, 현재고 계산, 권한, Admin 우회 방지, 테스트 기준을 명확히 한다.
```

---

## 1. 기술스택

| 구분 | 선택 |
|---|---|
| Backend | Django |
| Database | PostgreSQL |
| Frontend | Django Template |
| Admin | Django Admin |
| Authentication | Django 기본 인증 |
| Test DB | PostgreSQL |

v0.1에서 사용하지 않음:

```text
React, Next.js, DRF, FastAPI, Celery, Redis, 별도 모바일 앱, PIN 로그인
```

---

## 2. 프로젝트 구조

```text
gimpo365_inventory/
  manage.py
  config/
  core/
  accounts/
  inventory/
  templates/
  static/
  requirements.txt
  .env.example
  README.md
  PRODUCT_SPEC.md
  TECH_SPEC.md
  TASKS.md
```

앱 역할:

```text
config    → Django 설정, root URL, 환경변수
core      → 공통 모델. v0.1에서는 Department
accounts  → Custom User, 역할, 권한 헬퍼
inventory → 품목, 관리품목, 거래원장, 재고 로직, 화면, 폼, Admin
```

---

## 3. 절대 금지사항

```text
AUTH_USER_MODEL 설정 전 migrate 실행 금지
Django 기본 User로 첫 migration 생성 금지
SQLite로 테스트 실행 금지
SQLite에서 통과한 테스트를 완료 기준으로 인정 금지
StockTransaction.objects.create()를 View/Form/Admin에서 직접 호출 금지
transaction.status를 View/Form/Admin에서 직접 변경 후 save() 금지
Django Admin에서 StockTransaction add/delete 금지
Django Admin에서 StockTransaction managed_item/status/quantity_delta 직접 수정 금지
Profile 모델 생성 금지
Inventory Manager 그룹 v0.1 구현 금지
get_current_stock_for_update selector 생성 금지
```

---

## 4. Custom User 전략

최종 결정:

```text
Django 기본 User + Profile 방식 사용 안 함
accounts.User(AbstractUser) 사용
AUTH_USER_MODEL = "accounts.User"
```

첫 migration 전 순서:

```text
1. accounts 앱 생성
2. accounts.User(AbstractUser) 모델 작성
3. settings.py에 AUTH_USER_MODEL = "accounts.User" 설정
4. makemigrations 실행
5. migrate 실행
```

AbstractUser 상속 필드는 재정의하지 않는다.

```text
username, password, email, first_name, last_name, is_active, is_staff, is_superuser, date_joined, last_login
```

추가 필드:

| 필드 | 정책 |
|---|---|
| name | CharField(max_length=100, blank=True, default="") |
| department | ForeignKey(core.Department, null=True, blank=True, on_delete=SET_NULL) |
| role | CharField(max_length=20, choices=Role, default=STAFF) |
| created_at | auto_now_add |
| updated_at | auto_now |

`REQUIRED_FIELDS = []`

`create_superuser()`는 다음을 강제한다.

```text
role = ADMIN
is_staff = True
is_superuser = True
```

---

## 5. 권한 구조

Role:

```text
STAFF < TEAM_LEADER < MANAGER < ADMIN
```

점수:

```text
STAFF=10, TEAM_LEADER=20, MANAGER=30, ADMIN=40
```

개념 분리:

```text
role = 우리 운영 화면 권한
is_staff = Django Admin 출입증
is_superuser = Django Admin 전체 권한
```

v0.1 매핑:

| role | is_staff | is_superuser |
|---|---:|---:|
| STAFF | False | False |
| TEAM_LEADER | False | False |
| MANAGER | False | False |
| ADMIN | True | True |

부서 접근:

```text
STAFF / TEAM_LEADER → 본인 부서만
MANAGER / ADMIN → 전체 부서
```

권한 함수:

```python
def has_role_at_least(user, role: str) -> bool: ...
def is_manager_or_above(user) -> bool: ...
def is_admin_role(user) -> bool: ...
def can_access_managed_item(user, managed_item) -> bool: ...
def can_cancel_transaction(user, transaction_obj) -> bool: ...
```

---

## 6. 모델 확정

### 6.1 core.Department

| 필드 | 정책 |
|---|---|
| name | CharField(max_length=100, unique=True) |
| is_active | BooleanField(default=True) |
| active_for_inventory | BooleanField(default=True) |
| memo | TextField(blank=True, default="") |
| created_at | auto_now_add |
| updated_at | auto_now |

저장 전 `name.strip()` 적용.

---

### 6.2 inventory.Supplier

| 필드 | 정책 |
|---|---|
| name | CharField(max_length=150, unique=True) |
| phone | CharField(max_length=50, blank=True, default="") |
| homepage | URLField(max_length=255, blank=True, default="") |
| manager_name | CharField(max_length=100, blank=True, default="") |
| manager_phone | CharField(max_length=50, blank=True, default="") |
| memo | TextField(blank=True, default="") |
| is_active | BooleanField(default=True) |
| created_at | auto_now_add |
| updated_at | auto_now |

저장 전 `name.strip()` 적용. 삭제보다 비활성화 우선.

---

### 6.3 inventory.Item

| 필드 | 정책 |
|---|---|
| name | CharField(max_length=150, unique=True) |
| category | CharField(max_length=30, choices=ItemCategory), default 없음 |
| specification | CharField(max_length=150, blank=True, default="") |
| memo | TextField(blank=True, default="") |
| is_active | BooleanField(default=True) |
| created_at | auto_now_add |
| updated_at | auto_now |

결정:

```text
Item.name 단독 unique
specification은 설명용이며 unique 기준이 아니다.
구분 정보는 name에 포함한다.
예: 거즈 5x5, 거즈 10x10, 니들 30G
```

저장 전 `name.strip()` 적용.

---

### 6.4 inventory.ManagedItem

`ManagedItem = Department + Item`

| 필드 | 정책 |
|---|---|
| item | ForeignKey(Item, on_delete=PROTECT) |
| department | ForeignKey(Department, on_delete=PROTECT) |
| unit | CharField(max_length=20, choices=Unit, default=EA) |
| minimum_stock | DecimalField(max_digits=12, decimal_places=3, default=0) |
| storage_location | CharField(max_length=150, blank=True, default="") |
| default_supplier | ForeignKey(Supplier, null=True, blank=True, on_delete=PROTECT) |
| is_active | BooleanField(default=True) |
| memo | TextField(blank=True, default="") |
| created_at | auto_now_add |
| updated_at | auto_now |

제약:

```python
UniqueConstraint(fields=["department", "item"], name="uniq_managed_item_department_item")
```

unit 변경 금지:

```text
해당 ManagedItem에 APPROVED StockTransaction이 1건 이상 있으면 unit 변경 불가
모델 clean()에서 검증
Admin에서도 차단
```

---

### 6.5 inventory.StockTransaction

재고 거래 원장. 모든 재고 변동은 이 테이블에 기록한다.

현재고:

```text
현재고 = APPROVED StockTransaction.quantity_delta 합계
```

| 필드 | 정책 |
|---|---|
| managed_item | ForeignKey(ManagedItem, on_delete=PROTECT) |
| transaction_type | CharField(max_length=30, choices=TransactionType) |
| status | CharField(max_length=20, choices=TransactionStatus, default=PENDING) |
| quantity_input | DecimalField(max_digits=12, decimal_places=3, default=0) |
| quantity_delta | DecimalField(max_digits=12, decimal_places=3, default=0) |
| expected_quantity | DecimalField(max_digits=12, decimal_places=3, null=True, blank=True) |
| actual_quantity | DecimalField(max_digits=12, decimal_places=3, null=True, blank=True) |
| occurred_at | DateTimeField(default=timezone.now) |
| created_by | ForeignKey(User, on_delete=PROTECT, related_name="created_stock_transactions") |
| approved_by | ForeignKey(User, null=True, blank=True, on_delete=PROTECT, related_name="approved_stock_transactions") |
| approved_at | DateTimeField(null=True, blank=True) |
| supplier | ForeignKey(Supplier, null=True, blank=True, on_delete=PROTECT, related_name="stock_transactions") |
| unit_price | DecimalField(max_digits=12, decimal_places=2, null=True, blank=True) |
| expiration_date | DateField(null=True, blank=True) |
| reason | CharField(max_length=255, blank=True, default="") |
| review_note | TextField(blank=True, default="") |
| memo | TextField(blank=True, default="") |
| canceled_by | ForeignKey(User, null=True, blank=True, on_delete=PROTECT, related_name="canceled_stock_transactions") |
| canceled_at | DateTimeField(null=True, blank=True) |
| cancel_reason | TextField(blank=True, default="") |
| created_at | auto_now_add |
| updated_at | auto_now |

---

## 7. choices

```text
ItemCategory:
BEAUTY_SUPPLY, MEDICAL_SUPPLY, HYGIENE_SUPPLY, MEDICINE, GENERAL_SUPPLY, DEDICATED_SUPPLY, OTHER

Unit:
EA, BOX, PACK, P, ROLL, BOTTLE, VIAL, AMP, ML, G, KG, SET, OTHER

TransactionType:
INITIAL_COUNT, IN, OUT_USE, OUT_DISCARD, OUT_LOST, OUT_GIFT, OUT_OTHER, ADJUSTMENT

TransactionStatus:
PENDING, APPROVED, REJECTED, CANCELED
```

---

## 8. DB 제약조건 / 인덱스

Unique:

```text
Department.name unique
Supplier.name unique
Item.name unique
ManagedItem(department, item) unique
```

APPROVED INITIAL_COUNT 유일성:

```python
UniqueConstraint(
    fields=["managed_item"],
    condition=Q(transaction_type=TransactionType.INITIAL_COUNT, status=TransactionStatus.APPROVED),
    name="uniq_approved_initial_count_per_managed_item",
)
```

CheckConstraint:

```text
quantity_input >= 0
expected_quantity >= 0 또는 null
actual_quantity >= 0 또는 null
unit_price >= 0 또는 null
quantity_delta는 음수 가능하므로 >=0 제약 없음
```

확정 인덱스:

```python
Index(fields=["managed_item", "status"], name="idx_stock_tx_managed_item_status")
```

---

## 9. 재고 원장 규칙

quantity_delta:

```text
INITIAL_COUNT → +quantity
IN → +quantity
OUT_USE / OUT_DISCARD / OUT_LOST / OUT_GIFT / OUT_OTHER → -quantity
ADJUSTMENT → actual_quantity - expected_quantity
```

상태 전이:

```text
PENDING → APPROVED
PENDING → REJECTED
PENDING → CANCELED
APPROVED → CANCELED
REJECTED/CANCELED → 변경 불가
```

상태 변경은 service 함수로만 수행한다.

---

## 10. selector 함수

위치: `inventory/selectors.py`

```python
def get_current_stock(managed_item: ManagedItem) -> Decimal: ...
def get_accessible_managed_items(user: User): ...
def get_managed_items_with_current_stock(user: User, filters: dict | None = None): ...
def get_low_stock_managed_items(user: User, filters: dict | None = None): ...
def get_transactions(user: User, filters: dict | None = None): ...
def get_pending_transactions(user: User, filters: dict | None = None): ...
def has_approved_initial_count(managed_item: ManagedItem) -> bool: ...
```

원칙:

```text
selector는 순수 조회만 담당한다.
락을 걸지 않는다.
get_current_stock_for_update는 만들지 않는다.
```

---

## 11. service 함수

위치: `inventory/services.py`

```python
def create_stock_in(...): ...
def create_stock_out(...): ...
def request_adjustment(...): ...
def request_initial_count(...): ...
def approve_transaction(...): ...
def reject_transaction(...): ...
def withdraw_pending_transaction(...): ...
def cancel_transaction(...): ...
def bulk_approve_initial_counts(...): ...
```

공통 원칙:

```text
재고 원장 변경은 반드시 service 함수로 수행
권한 검사
상태 전이 검사
현재고 음수 방지
동시성 처리
감사 필드 기록
```

핵심 규칙:

```text
create_stock_in: STAFF 이상, APPROVED IN, quantity_delta=+quantity
create_stock_out: STAFF 이상, OUT 계열만, 현재고-quantity >= 0
request_adjustment: STAFF 이상, PENDING, expected_quantity 저장, delta=actual-expected, reason 필수
request_initial_count: STAFF/TL=PENDING, MANAGER/ADMIN=APPROVED, APPROVED INITIAL_COUNT 중복 차단
approve_transaction: MANAGER 이상, PENDING INITIAL_COUNT/ADJUSTMENT만, row lock, 중복/음수 검증
reject_transaction: MANAGER 이상, row lock, review_note 필수
withdraw_pending_transaction: 생성자 또는 MANAGER 이상, row lock, cancel_reason 필수
cancel_transaction: APPROVED 일반 거래만, 취소 후 현재고>=0
bulk_approve_initial_counts: PENDING INITIAL_COUNT 대상, 거래별 savepoint, 부분 성공 허용
```

---

## 12. Forms

생성 Form은 반드시 user-aware Form으로 구현한다.

대상:

```text
StockInForm
StockOutForm
AdjustmentRequestForm
InitialCountForm
```

원칙:

```text
form = StockInForm(user=request.user, data=request.POST or None)
managed_item queryset = get_accessible_managed_items(user)
STAFF StockInForm에는 unit_price 필드 없음
occurred_at 기본값 = timezone.now
occurred_at은 미래일 수 없음
```

---

## 13. View / URL

URL:

```text
/
accounts/login/
accounts/logout/
inventory/dashboard/
inventory/stock/
inventory/low-stock/
inventory/transactions/
inventory/in/new/
inventory/out/new/
inventory/adjustment/new/
inventory/initial-count/new/
inventory/pending/
inventory/pending/<int:pk>/approve/
inventory/pending/<int:pk>/reject/
inventory/pending/<int:pk>/withdraw/
inventory/transactions/<int:pk>/cancel/
inventory/initial-counts/bulk-approve/
```

View 원칙:

```text
View는 service 함수 호출만 수행
StockTransaction 직접 create/save 금지
상태 변경은 POST에서만 수행
GET은 확인 Form 렌더링만 수행
모든 상태 변경 POST는 CSRF 필요
버튼 숨김은 UX일 뿐, View GET/POST에서 권한 재검사
```

입고/출고 성공 후:

```text
같은 Form에 머무름 + 성공 메시지
```

초기재고 일괄 승인:

```text
승인 큐 화면에 체크박스 통합
PENDING INITIAL_COUNT만 일괄 승인 대상
```

---

## 14. Django Admin

v0.1 원칙:

```text
Django Admin은 ADMIN 전용
Inventory Manager 그룹은 만들지 않음
활성 ADMIN 계정 최소 2개 권장
```

StockTransactionAdmin:

```text
add 금지
delete 금지
change 제한
조회 중심
```

readonly 필드:

```text
managed_item
transaction_type
status
quantity_input
quantity_delta
expected_quantity
actual_quantity
occurred_at
created_by
approved_by
approved_at
supplier
unit_price
expiration_date
canceled_by
canceled_at
created_at
updated_at
```

마스터 데이터:

```text
User, Department, Supplier, Item, ManagedItem → ADMIN 전용
삭제보다 is_active=False 비활성화 우선
```

---

## 15. 테스트 정책

```text
테스트는 반드시 PostgreSQL에서 실행
SQLite 테스트 금지
SQLite에서 통과한 테스트는 완료 기준으로 인정하지 않음
```

P0/P1/P2:

```text
P0 = 출시 게이트. 전부 통과해야 v0.1 운영 가능
P1 = 실제 직원 투입 전 통과 권장
P2 = 수동 체크 가능
```

자동화 필수:

```text
모델 제약조건
selector
service
permission
form
view 권한
admin 안전장치
APPROVED INITIAL_COUNT 유일성
bulk approve 부분 성공
감사 필드 기록
실사조정 delta 정합성
```

수동/통합 검증:

```text
락 타이밍 기반 동시성
화면 카피
사용자 안내 문구
디자인/레이아웃
연속 입력 UX
```

---

## 16. 폐기된 결정

구현하지 않는다.

```text
Django 기본 User + Profile 방식
inventory.Department 배치
Item name + specification unique
Inventory Manager 그룹 v0.1 구현
SQLite 테스트
get_current_stock_for_update selector
StockTransaction Admin add 허용
Generic CreateView/UpdateView로 ModelForm.save() 직접 사용
View/Form/Admin에서 StockTransaction 직접 create/save
```

---

## 17. 다음 단계

다음 문서는 `TASKS.md`다.

TASKS.md는 다음을 포함한다.

```text
확정 사실
폐기 결정
절대 금지사항
작업 순서
각 TASK 완료 기준
연결 테스트 ID
Codex/Claude Code 지시문
```
