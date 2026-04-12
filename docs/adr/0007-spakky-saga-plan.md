# ADR-0007: spakky-saga — 분산 트랜잭션 사가 오케스트레이션 코어 패키지

- **상태**: Proposed
- **날짜**: 2026-04-05

## 맥락 (Context)

현재 Spakky Framework는 `@Transactional`을 통해 단일 서비스/단일 DB 범위의 트랜잭션을 지원한다.
그러나 복수 서비스를 아우르는 분산 트랜잭션(예: 주문 생성 → 티켓 발행 → 결제 승인)은 프레임워크 수준의 지원이 없어, 개발자가 보상 로직과 실패 처리를 직접 구현해야 한다.

이 문제를 해결하기 위해 코어 패키지 `spakky-saga`를 도입한다.

### 사가와 RDB 트랜잭션의 차이

| 성질 | RDB Transaction | Saga |
|---|---|---|
| Atomicity | 즉시 all-or-nothing | 최종적 all-or-nothing |
| Consistency | 강한 일관성 | 최종 일관성 |
| Isolation | ✅ 중간 상태 비노출 | ❌ **중간 상태 노출** |
| Durability | ✅ | ✅ (영속화에 의존) |

Isolation 갭 대응: **Semantic Lock** 패턴 권장 (PENDING → CONFIRMED).

### 선행 조사

| 프레임워크 | 영향 받은 부분 |
|---|---|
| Eventuate Tram (FTGO) | step-based 순차 구조 |
| Axon Framework | 스테레오타입 기반 사가 정의 |
| Temporal Python SDK | async/await 네이티브, typed I/O |
| MassTransit | 상태 머신, 동시성 제어 |
| NServiceBus | 메시지 상관관계, 사가 라이프사이클 |
| MS CQRS Journey | Process Manager vs Saga 용어 구분 |
| microservices.io | Compensable/Pivot/Retryable 트랜잭션 분류 |

## 결정 동인 (Decision Drivers)

- **DX 최우선**: 개발자가 쓰기 쉽고, 알기 쉬우며, 실수할 가능성이 없는 인터페이스
- **기존 패턴 일관성**: `@UseCase()`, `Pod`, `@immutable` 등 기존 Spakky 관용어 재사용
- **관심사 분리**: Saga는 순수 흐름 제어기, 비즈니스 로직은 UseCase에 위임
- **타입 안전성**: 리턴 타입을 통한 컴파일 타임 검증, 런타임 마법 최소화
- **점진적 복잡도**: v1은 핵심 기능만, 고급 기능은 v2로 분리

## 고려한 대안 (Considered Options)

### 대안 A: 상태 머신 기반 사가

MassTransit/NServiceBus 스타일. 상태 전이 테이블을 정의하고 이벤트에 반응하는 방식.

```python
class CreateOrderSaga(StateMachine):
    pending = State(initial=True)
    ticket_created = State()
    completed = State(final=True)

    create_ticket = pending.to(ticket_created)
    approve_order = ticket_created.to(completed)
```

- **장점**: 복잡한 분기/재진입 표현 가능, 시각화 용이
- **단점**: 대부분의 사가는 선형 순차 흐름인데 상태 머신은 과도한 추상화. 보상 로직이 상태 전이에 흩어져 가독성 저하. DX 복잡도 높음.

### 대안 B: 데코레이터 기반 step 정의

Spring Modulith / Axon 스타일. 각 step을 메서드 데코레이터로 마킹하고 프레임워크가 순서를 추론.

```python
@Saga()
class CreateOrderSaga:
    @step(order=1, compensate="reject_order")
    async def validate_order(self, data): ...

    @step(order=2, compensate="cancel_ticket")
    async def create_ticket(self, data): ...
```

- **장점**: 한 메서드가 한 step, 구조 명확
- **단점**: 흐름의 전체 그림이 분산됨. 순서를 `order=` 정수로 관리하면 삽입/삭제 시 번호 재정렬 필요. `compensate="문자열"`은 타입 안전하지 않음.

### 대안 C: flow builder 패턴 (채택)

Eventuate Tram / Temporal 스타일. 단일 메서드에서 전체 흐름을 선언적으로 정의.

```python
def flow(self) -> SagaFlow[CreateOrderSagaData]:
    return saga_flow(
        step(self.validate, compensate=self.reject),
        step(self.create_ticket, compensate=self.cancel_ticket),
        step(self.authorize_payment),
        step(self.approve_order),
    )
```

- **장점**: 전체 흐름이 한 곳에 모임. 함수 참조로 타입 안전. 연산자 syntax sugar로 간결함 제공 가능.
- **단점**: 메서드가 많아지면 `flow()` 아래로 스크롤해야 각 step 구현을 볼 수 있음 (IDE 지원으로 완화).

## 결정 (Decision)

**대안 C — flow builder 패턴을 채택한다.**

### 패키지 개요

| 항목 | 내용 |
|---|---|
| 이름 | `spakky-saga` |
| 종류 | **코어 패키지** (`core/spakky-saga/`) |
| 역할 | 분산 트랜잭션 사가 오케스트레이션 |
| 의존 | `spakky` (DI/AOP), `spakky-domain` (AbstractDomainModel, @immutable) |
| Python | 3.11+ |

### 아키텍처 위치

```
Controller
  ├── UseCase      ← 단일 Aggregate, 로컬 @Transactional
  └── Saga         ← 복수 서비스, 분산 트랜잭션 오케스트레이션 (NEW)
        │
        ├── UseCase 호출    (내부 서비스 위임)
        └── Command 발행    (외부 서비스)
```

- `@Saga()`는 `@UseCase()`와 **동급**의 application layer 스테레오타입
- `Pod`을 상속하므로 DI 컨테이너가 동일하게 관리
- Controller에서 UseCase 또는 Saga를 직접 주입받아 호출

스테레오타입 계층:

```
Pod
├── UseCase           단일 비즈니스 오퍼레이션
├── Saga              분산 트랜잭션 오케스트레이션  ← NEW
├── Controller        외부 요청 수신
├── Repository        데이터 접근
├── EventHandler      이벤트 처리
├── TaskHandler       비동기 태스크
└── Configuration     설정/팩토리
```

### Saga의 역할 제한 (순수 흐름 제어기)

```
Saga가 하는 것:
  ✓ UseCase를 호출한다 (내부 서비스)
  ✓ Command를 발행한다 (외부 서비스)
  ✓ 실패 시 보상 흐름을 실행한다
  ✓ step 간 데이터를 전달한다 (SagaData)

Saga가 하지 않는 것:
  ✗ Repository 직접 접근
  ✗ Aggregate 직접 조작
  ✗ 비즈니스 규칙 판단
  ✗ 트랜잭션 관리 (@Transactional은 UseCase가 담당)
```

각 step의 실체: **UseCase 호출 1줄 + data 리턴 1줄**.
비즈니스 로직과 영속성 제어는 모두 UseCase/Aggregate에 위임.

### 사용자 API 설계

#### SagaData (immutable)

`AbstractSagaData`는 순수 비즈니스 데이터만 포함한다.
엔진 상태(`status`, `current_step` 등)는 `SagaResult`가 관리하며, 사용자 데이터와 분리된다.

```python
@immutable
class AbstractSagaData(AbstractDomainModel):
    """사가의 비즈니스 데이터. 엔진 상태를 포함하지 않는다."""
    saga_id: UUID = field(default_factory=uuid4)


@immutable
class CreateOrderSagaData(AbstractSagaData):
    order_id: OrderId
    ticket_id: TicketId | None = None
    payment_id: PaymentId | None = None
```

#### Saga 정의 (핵심 DX)

`AbstractSaga.flow()`는 `@abstractmethod`로 정의한다.
별도 마커 데코레이터(`@definition`)는 사용하지 않는다 — 추상 메서드만으로 충분하다.

```python
@Saga()
class CreateOrderSaga(AbstractSaga[CreateOrderSagaData]):
    def __init__(
        self,
        validate_order: ValidateOrderUseCase,
        create_ticket: CreateTicketUseCase,
        authorize_payment: AuthorizePaymentUseCase,
        approve_order: ApproveOrderUseCase,
        reject_order: RejectOrderUseCase,
        cancel_ticket: CancelTicketUseCase,
    ) -> None:
        self._validate_order = validate_order
        self._create_ticket = create_ticket
        self._authorize_payment = authorize_payment
        self._approve_order = approve_order
        self._reject_order = reject_order
        self._cancel_ticket = cancel_ticket

    def flow(self) -> SagaFlow[CreateOrderSagaData]:
        return saga_flow(
            # 함수 기반: 가장 명시적
            step(
                lambda d: self._validate_order.execute(d.order_id),
                compensate=lambda d: self._reject_order.execute(d.order_id),
            ),
            # 연산자: syntax sugar (>> = step with compensate)
            self.create_ticket >> self.cancel_ticket,
            # 단독 step: rollback 없음
            lambda d: self._authorize_payment.execute(d.order_id),
            lambda d: self._approve_order.execute(d.order_id),
        )

    # data 변환이 필요한 것만 메서드로
    async def create_ticket(self, data: CreateOrderSagaData) -> CreateOrderSagaData:
        ticket_id = await self._create_ticket.execute(data.order_id)
        return replace(data, ticket_id=ticket_id)

    async def cancel_ticket(self, data: CreateOrderSagaData) -> None:
        if data.ticket_id is not None:
            await self._cancel_ticket.execute(data.ticket_id)
```

#### 연산자 syntax sugar

연산자는 함수 기반 API의 **syntax sugar**이다. 명확성이 중요한 경우 함수 기반 호출을 사용한다.

| 연산자 | 함수 등가 | 의미 | Python 우선순위 |
|---|---|---|---|
| `a >> b` | `step(a, compensate=b)` | 하고, 실패하면 되돌려 | 1 (높음) |
| `a & b` | `parallel(a, b)` | 동시에 실행 | 2 |
| `x \| E` | `step(..., on_error=E)` | 에러 전략 지정 | 3 (낮음) |
| `,` | — | 순차 실행 | N/A |

**연산자 래핑 메커니즘**: 사가 step 역할의 async 메서드에 `@saga_step` 데코레이터를 명시적으로 적용한다. 데코레이터가 `_SagaStepDescriptor[SagaDataT]`를 반환하여, 인스턴스 접근 시 overload된 `__get__`이 `SagaStep[SagaDataT]`을 돌려준다. 이 설계는 타입체커가 연산자 `>>`, `&`, `|`를 정적으로 추적할 수 있게 하며 `# type: ignore` 주석이 필요 없다.

연산자와 함수를 자유롭게 혼합 가능:

```python
saga_flow(
    # 연산자
    self.validate >> self.reject,
    # 함수
    step(lambda d: ..., compensate=lambda d: ...),
    # 에러 전략 (연산자)
    self.pay >> self.refund | Retry(3),
    # 에러 전략 (함수)
    step(self.pay, compensate=self.refund, on_error=Retry(3)),
    # 병렬 (함수, 명시적)
    parallel(
        lambda d: self._create_ticket.execute(d.order_id),
        lambda d: self._authorize_payment.execute(d.order_id),
    ),
    # 단독
    lambda d: self._approve.execute(d.order_id),
)
```

**주의**: 연산자를 복잡하게 조합하면 우선순위 파악이 어려워진다. 병렬 + 에러 전략이 섞이는 경우 함수 기반을 권장한다:

```python
# ✗ 비권장: 우선순위 혼동 가능
self.a >> self.b & self.c >> self.d | Retry(3)
# 실제 파싱: (self.a >> self.b) & ((self.c >> self.d) | Retry(3))

# ✓ 권장: 함수로 명시
parallel(
    step(self.a, compensate=self.b),
    step(self.c, compensate=self.d, on_error=Retry(3)),
)
```

#### saga_flow에 넣을 수 있는 FlowItem

| 형태 | 의미 |
|---|---|
| `commit` (메서드) | 순차 실행, rollback 없음 |
| `lambda d: ...` | 순차 실행, rollback 없음 (자동 승격) |
| `commit >> rollback` | 순차 실행, rollback 있음 |
| `step(commit, compensate=rollback)` | 위와 동일 (함수 표현) |
| `x \| ErrorStrategy` | 에러 전략 지정 |
| `a & b` / `parallel(a, b, ...)` | 동시 실행 |

#### 람다 자동 처리 규칙

사가 엔진이 람다/메서드의 리턴값을 자동 처리한다:

- 결과가 `SagaData` 서브타입이면 → 새 data로 교체
- 결과가 `SagaData`가 아니면 (`None` 포함) → 기존 data 그대로 통과

이는 Python의 타입 시스템만으로는 두 역할(data 변환 / side-effect)을 하나의 `Callable`로 깔끔하게 구분할 수 없기 때문에 도입한 런타임 편의 기능이다.

### 에러 처리 전략

#### 에러 계층

`spakky-saga` 전용 에러 계층을 정의한다:

```python
class AbstractSpakkySagaError(AbstractSpakkyFrameworkError, ABC):
    """spakky-saga 패키지의 모든 에러 기반 클래스."""

class SagaFlowDefinitionError(AbstractSpakkySagaError):
    """flow 정의가 올바르지 않을 때 (정적 검증)."""
    message = "Invalid saga flow definition"

class SagaCompensationFailedError(AbstractSpakkySagaError):
    """보상 실행 중 에러 발생 (on_compensation_failure 미설정 시)."""
    message = "Saga compensation failed"

class SagaParallelMergeConflictError(AbstractSpakkySagaError):
    """v2: 병렬 step의 data 자동 병합 시 필드 충돌."""
    message = "Parallel steps modified the same field"
```

#### on_error 전략 (단일 파라미터)

step 실패 시 대응을 `on_error` 하나로 표현한다:

| 전략 | 의미 | 기본값 |
|---|---|---|
| `Compensate` | 역순 rollback 시작 | ✓ 기본 |
| `Skip` | 무시하고 다음 step으로 | — |
| `Retry(max_attempts, backoff, then)` | N회 재시도 후 `then` 전략 실행 | `then=Compensate` |

`Retry.then`으로 "재시도 소진 후 동작"을 명시한다. `retry`와 `on_error`를 별도 파라미터로 두지 않음으로써 조합 모호성을 제거한다.

```python
# 결제: 3회 재시도 후 보상 (기본)
step(
    lambda d: self._pay.execute(d.order_id),
    compensate=lambda d: self._refund.execute(d.payment_id),
    on_error=Retry(max_attempts=3, backoff=exponential(base=1.0)),
)

# 알림: 2회 재시도 후 스킵
step(
    lambda d: self._notify.execute(d.order_id),
    on_error=Retry(max_attempts=2, then=Skip),
)

# 알림: 즉시 스킵
step(
    lambda d: self._notify.execute(d.order_id),
    on_error=Skip,
)
```

의사결정 흐름:
```
step 실패
  → on_error가 Retry?
      → 재시도 (max_attempts까지)
      → 전부 실패 → then 전략 적용 (기본: Compensate)
  → on_error가 Skip?       → 다음 step으로
  → on_error가 Compensate? → 역순 보상 시작
```

연산자로 표현:
```python
self.pay >> self.refund | Retry(3)           # 3회 재시도 후 보상
self.notify | Retry(2, then=Skip)            # 2회 재시도 후 스킵
self.notify | Skip                           # 즉시 스킵
```

#### 타임아웃

```python
# step 타임아웃
step(lambda d: ..., timeout=timedelta(seconds=30))

# saga 전체 타임아웃
saga_flow(...).timeout(timedelta(minutes=5))
```

#### 보상 실패 대응

```python
saga_flow(...).on_compensation_failure(self.escalate)
```

`on_compensation_failure`가 설정되지 않은 상태에서 보상이 실패하면 `SagaCompensationFailedError`를 발생시킨다.

#### 실행 결과 (예외 미발생)

Saga 실패는 정상적인 비즈니스 결과이므로 예외를 throw하지 않는다.
엔진 상태(`status`, `current_step`, `created_at` 등)는 `SagaResult`가 관리한다:

```python
result: SagaResult[CreateOrderSagaData] = await saga.execute(data)

result.status       # COMPLETED | FAILED | TIMED_OUT
result.data         # 최종 SagaData (비즈니스 데이터)
result.failed_step  # 실패한 step 이름 (또는 None)
result.error        # 원인 예외 (AbstractSpakkySagaError | None)
result.history      # 실행된 step 목록 + 각 소요 시간
result.elapsed      # 사가 전체 소요 시간
```

`SagaStatus`는 엔진 내부에서 추적하며 `SagaResult.status`로 노출된다:

```python
class SagaStatus(Enum):
    STARTED = "STARTED"
    RUNNING = "RUNNING"
    COMPENSATING = "COMPENSATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
```

### 실행 흐름

```
정상:
  Step#0 commit ✓ → Step#1 commit ✓ → Step#2 commit ✓ → COMPLETED

Step#1 실패:
  Step#0 commit ✓ → Step#1 commit ✗ → Step#0 compensate → FAILED
                    (compensate가 있는 step만 역순으로)

Step#2 실패 + retry:
  Step#0 ✓ → Step#1 ✓ → Step#2 ✗ → retry → Step#2 ✗ → retry → Step#2 ✓ → COMPLETED
                          또는 max_attempts 초과
                          → then 전략 적용 (Compensate: Step#1 compensate → Step#0 compensate → FAILED)

병렬 실패:
  Step#0 ✓ → parallel(Step#1a ✓, Step#1b ✗) → Step#1a compensate → Step#0 compensate → FAILED
              (하나라도 실패하면 성공한 것도 compensate)
```

### 병렬 step의 data 처리

v1에서 병렬 step은 **side-effect only**로 제한한다. 리턴값을 무시하고, 각 UseCase가 자체적으로 영속화한다.

```python
saga_flow(
    self.validate_order >> self.reject_order,
    # 병렬: side-effect only (각 UseCase가 DB에 저장)
    parallel(
        lambda d: self._create_ticket.execute(d.order_id),
        lambda d: self._authorize_payment.execute(d.order_id),
    ),
    # 필요하면 직후에 조회
    self.fetch_order_details,   # DB에서 ticket_id, payment_id 읽어서 data에 채움
    self.approve_order,
)
```

**병합 문제가 존재하기 때문이다**: 병렬 step들이 같은 input data를 받아 각자 다른 필드를 변경하면, 엔진이 두 결과를 어떻게 합칠지 자동으로 결정할 수 없다. 같은 필드를 둘 다 수정하는 경우는 원천적으로 병합 불가능하다.

v2에서 field-diff 기반 자동 병합 + 명시적 `merge=` escape hatch를 추가할 수 있다.

### 관측성

구조화 로그 자동 출력 (`spakky-logging` 연동):

```
[saga=CreateOrderSaga step=validate status=started]
[saga=CreateOrderSaga step=validate status=completed elapsed=12ms]
[saga=CreateOrderSaga step=ticket status=failed error=TimeoutError]
[saga=CreateOrderSaga step=validate status=compensating]
[saga=CreateOrderSaga status=FAILED elapsed=1.2s]
```

### 내부 타입 시스템

```python
SagaDataT = TypeVar("SagaDataT", bound=AbstractSagaData)

# 시그니처 규칙
ActionFn     = Callable[[SagaDataT], Awaitable[SagaDataT | Any]]  # commit: data 변환 가능
CompensateFn = Callable[[SagaDataT], Awaitable[None]]             # 보상만

# 핵심 타입
SagaStep[T]        # 개별 step (메서드 또는 람다 래핑)
Transaction[T]     # commit + compensate 쌍 (>> 연산자 결과)
Parallel[T]        # 동시 실행 그룹 (& 연산자 결과)
SagaFlow[T]        # 전체 흐름 정의
SagaResult[T]      # 실행 결과

# FlowItem 유니온
FlowItem = SagaStep[T] | Transaction[T] | Parallel[T] | Callable[[T], Awaitable]

# 에러 전략
ErrorStrategy = Compensate | Skip | Retry

# 연산자
SagaStep.__rshift__(compensate)  → Transaction   # >>
SagaStep.__and__(other)          → Parallel      # &
Transaction.__and__(other)       → Parallel      # &
Parallel.__and__(other)          → Parallel      # & (추가)
SagaStep.__or__(strategy)        → SagaStep      # | (on_error 설정)
Transaction.__or__(strategy)     → Transaction   # | (on_error 설정)
```

### v1 스코프

#### 포함

| 기능 | 설명 |
|---|---|
| `@Saga()` 스테레오타입 | Pod 상속, DI 관리 |
| `AbstractSaga[T]` | 제네릭 베이스 클래스, `flow()` 추상 메서드 |
| `AbstractSagaData` | immutable 비즈니스 데이터 모델 (`saga_id`만 포함) |
| `saga_flow()` | 순차 실행 정의 |
| `step(action, compensate=)` | commit-compensate 바인딩 |
| `>>` / `&` / `\|` 연산자 | 함수 기반 API의 syntax sugar |
| `parallel()` | 동시 실행 (side-effect only) |
| 람다 + 메서드 혼합 | FlowItem 자동 승격 |
| `SagaResult[T]` | 예외 미발생 결과 객체 (엔진 상태 포함) |
| `on_error` 단일 파라미터 | `Compensate` / `Skip` / `Retry(then=)` |
| `timeout` per step/saga | step 및 사가 전체 타임아웃 |
| `.on_compensation_failure(fn)` | 보상 실패 에스컬레이션 |
| `AbstractSpakkySagaError` 계층 | 사가 전용 에러 |
| 구조화 로그 | `spakky-logging` 연동 |

#### v2로 미룸

| 기능 | 사유 |
|---|---|
| 병렬 step data 병합 (`merge=`) | 병합 전략의 복잡도, v1은 side-effect only로 충분 |
| `branch(cond, then, otherwise)` | 순차/병렬로 대부분 해결 |
| `.on_completed()` / `.on_failed()` | `SagaResult`로 대체 가능 |
| 상태 영속화 (crash resume) | 복잡도 큼 |
| 트레이싱 Span 자동 생성 | `spakky-tracing` 의존 |
| 분산 실행 (MQ 경유 step) | 아키텍처 확장 |

## 결과 (Consequences)

### 긍정적

- `@UseCase()`와 동일한 패턴으로 분산 트랜잭션을 선언적으로 정의할 수 있다
- flow builder 패턴으로 전체 흐름을 한 곳에서 파악할 수 있다
- `SagaResult`로 실패를 정상적인 비즈니스 결과로 처리한다 (예외 미발생)
- `on_error` 단일 파라미터로 에러 전략의 조합 모호성을 제거한다
- 엔진 상태와 비즈니스 데이터 분리로 `AbstractSagaData`의 오용 가능성 제거

### 부정적

- 연산자 syntax sugar(`>>`, `&`, `|`)가 Python 기본 문법이 아니므로 학습 비용 발생
- `@saga_step` 데코레이터를 모든 step 메서드에 명시적으로 붙여야 한다 (대신 타입 안전성을 얻는다)
- v1에서 병렬 step이 side-effect only로 제한되어, 일부 패턴에서 추가 조회 step 필요

### 중립적

- 코어 패키지 1개 추가 (`spakky-saga`)
- `spakky-domain`에 대한 의존 추가 (`AbstractDomainModel`, `@immutable`)

## 참고 자료

- [Chris Richardson — Microservices Patterns (Chapter 4: Saga)](https://microservices.io/patterns/data/saga.html)
- [Eventuate Tram Sagas](https://eventuate.io/docs/manual/eventuate-tram/latest/getting-started-eventuate-tram-sagas.html)
- [Temporal Python SDK](https://docs.temporal.io/develop/python)
- [FTGO Example Application](https://github.com/microservices-patterns/ftgo-application)
