# Spakky Framework 용어 사전

이 문서는 Spakky Framework에서 사용하는 핵심 용어를 정의합니다.

---

## 코어 개념

### Pod

컨테이너가 관리하는 컴포넌트 단위. `@Pod` 데코레이터로 클래스나 함수를 표시하면 `ApplicationContext`가 인스턴스 생명주기와 의존성 주입을 담당합니다.

```python
from spakky.core.pod.annotations.pod import Pod

@Pod()
class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository
```

**스코프 (Scope)**:

- `SINGLETON` — 애플리케이션 전체에서 하나의 인스턴스 공유 (기본값)
- `PROTOTYPE` — 요청할 때마다 새 인스턴스 생성
- `CONTEXT` — 요청/컨텍스트 범위 내에서 인스턴스 공유

### ApplicationContext

Pod 인스턴스와 생명주기를 관리하는 핵심 컨테이너. 의존성 주입, 서비스 시작/종료, 이벤트 루프 관리를 담당합니다.

```python
from spakky.core.application.application_context import ApplicationContext

context = ApplicationContext()
context.add(UserService)
context.start()
```

### Optional DI (`get_or_none`)

컨테이너에 등록되어 있지 않을 수 있는 Pod를 안전하게 조회하는 패턴입니다. `ApplicationContext.get_or_none(type_)`은 Pod가 등록되어 있으면 인스턴스를 반환하고, 없으면 `None`을 반환합니다. `get()`과 달리 `NoSuchPodError`를 발생시키지 않습니다.

```python
from spakky.core.pod.interfaces.container import IContainer

propagator = container.get_or_none(ITracePropagator)
if propagator is not None:
    propagator.inject(carrier)
```

이 패턴은 플러그인 간 선택적 의존성에 사용됩니다. 예를 들어, `spakky-fastapi`의 `AddBuiltInMiddlewaresPostProcessor`는 `get_or_none(ITracePropagator)`로 propagator를 조회하고, 있으면 `TracingMiddleware`를 등록합니다.

### SpakkyApplication

애플리케이션 부트스트랩 진입점. 컴포넌트 스캔, 플러그인 로딩, 컨테이너 설정을 위한 fluent API를 제공합니다.

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

app = SpakkyApplication(ApplicationContext())
app.scan()  # 현재 패키지의 Pod 자동 스캔
```

---

## Stereotype 데코레이터

Pod의 역할을 명시하는 특화된 데코레이터입니다. 기능적으로 `@Pod`와 동일하지만 의도를 명확히 합니다.

### @Configuration

팩토리 메서드를 포함하는 설정 클래스. 다른 Pod를 생성하는 `@Pod` 메서드를 그룹화합니다.

```python
from spakky.core.stereotype.configuration import Configuration
from spakky.core.pod.annotations.pod import Pod

@Configuration()
class DatabaseConfig:
    @Pod()
    def connection_pool(self) -> ConnectionPool:
        return ConnectionPool(size=10)
```

### @Controller

외부 요청을 처리하는 클래스 (HTTP, CLI 등).

```python
from spakky.core.stereotype.controller import Controller

@Controller()
class UserController:
    def __init__(self, service: UserService) -> None:
        self.service = service
```

### @UseCase

비즈니스 로직을 캡슐화하는 애플리케이션 서비스.

```python
from spakky.core.stereotype.usecase import UseCase

@UseCase()
class CreateUserUseCase:
    def execute(self, command: CreateUserCommand) -> User:
        ...
```

### @Repository

데이터 접근 계층. 영속성 저장소와의 상호작용을 추상화합니다.

```python
from spakky.data.stereotype.repository import Repository

@Repository()
class UserRepository:
    def find_by_id(self, id: UUID) -> User | None:
        ...
```

### @EventHandler

이벤트를 처리하는 클래스. `@on_event` 데코레이터와 함께 사용합니다.

```python
from spakky.event.stereotype.event_handler import EventHandler, on_event

@EventHandler()
class UserEventHandler:
    @on_event(UserCreatedEvent)
    async def handle(self, event: UserCreatedEvent) -> None:
        ...
```

---

## AOP (관점 지향 프로그래밍)

### Aspect

횡단 관심사 (로깅, 트랜잭션 등)를 모듈화하는 컴포넌트. `IAspect` 또는 `IAsyncAspect` 인터페이스를 구현합니다.

```python
from spakky.core.aop.aspect import Aspect
from spakky.core.aop.interfaces.aspect import IAspect

@Aspect()
class LoggingAspect(IAspect):
    def before(self, *args, **kwargs) -> None:
        print("Method called")
```

### Advice

Aspect가 특정 시점에 실행하는 액션:

- **Before** — 메서드 실행 전
- **AfterReturning** — 메서드 정상 반환 후
- **AfterRaising** — 메서드 예외 발생 후
- **After** — 메서드 실행 후 (결과와 무관)
- **Around** — 메서드 실행을 감싸서 제어

### Pointcut

Advice가 적용될 메서드를 선택하는 조건자 함수.

```python
from spakky.core.aop.pointcut import Around

def is_service_method(method) -> bool:
    return hasattr(method, "__service__")

@Around(pointcut=is_service_method)
def around(self, joinpoint, *args, **kwargs):
    return joinpoint(*args, **kwargs)
```

### JoinPoint

Aspect가 개입할 수 있는 프로그램 실행 지점. Around advice에서 다음 호출을 제어할 때 사용합니다.

---

## 도메인 모델 (spakky-domain)

### Entity

고유 식별자로 구분되는 도메인 객체. `AbstractEntity`를 상속합니다.

```python
from spakky.domain.models.entity import AbstractEntity

@mutable
class User(AbstractEntity[UUID]):
    name: str
    email: str
```

### ValueObject

식별자 없이 속성값으로만 동등성을 판단하는 불변 객체. `AbstractValueObject`를 상속합니다.

```python
from spakky.domain.models.value_object import AbstractValueObject

@immutable
class Email(AbstractValueObject):
    value: str
```

### AggregateRoot

일관성 경계를 관리하는 엔터티의 진입점. 도메인 이벤트를 수집하고 발행합니다. `AbstractAggregateRoot`를 상속합니다.

```python
from spakky.domain.models.aggregate_root import AbstractAggregateRoot

@mutable
class Order(AbstractAggregateRoot[UUID]):
    items: list[OrderItem]

    def add_item(self, item: OrderItem) -> None:
        self.items.append(item)
        self.add_event(ItemAddedEvent(order_id=self.uid, item=item))
```

---

## 이벤트 시스템 (spakky-event)

> 설계 배경 및 대안 분석은 [ADR-0001](adr/0001-event-system-redesign.md)을 참조하세요.

### DomainEvent

하나의 바운디드 컨텍스트 내에서 발생하는 도메인 상태 변경. `AbstractDomainEvent`를 상속합니다.

```python
from spakky.domain.models.event import AbstractDomainEvent

@immutable
class UserCreatedEvent(AbstractDomainEvent):
    user_id: UUID
    email: str
```

### IntegrationEvent

바운디드 컨텍스트 간 또는 서비스 간 통신에 사용되는 이벤트. `AbstractIntegrationEvent`를 상속합니다.

```python
from spakky.domain.models.event import AbstractIntegrationEvent

@immutable
class OrderPlacedEvent(AbstractIntegrationEvent):
    order_id: UUID
    total_amount: Decimal
```

### 동사 규칙 (Verb Convention) { #동사-규칙-verb-convention }

이벤트 시스템 전체에서 동사를 다음과 같이 구분합니다:

| 동사 | 의미 | 사용 레이어 |
|------|------|------------|
| `publish` | 이벤트를 시스템에 발행 (호출자가 경로를 모름) | EventPublisher |
| `send` | Integration Event를 외부로 전송 | EventBus, EventTransport |
| `dispatch` | 등록된 핸들러에 인프로세스 전달 | Dispatcher, Mediator |
| `register` | 이벤트 타입에 핸들러 콜백 등록 | Consumer |

### 이벤트 인터페이스

> 설계 배경은 [ADR-0001](adr/0001-event-system-redesign.md) 참조.

| 역할 | 인터페이스 (sync / async) | 설명 |
|------|--------------------------|------|
| 발행 진입점 | `IEventPublisher` / `IAsyncEventPublisher` | 타입 기반 라우팅 |
| 인프로세스 전달 | `IEventDispatcher` / `IAsyncEventDispatcher` | 핸들러에 dispatch |
| 핸들러 등록 | `IEventConsumer` / `IAsyncEventConsumer` | 콜백 등록 |
| 외부 전송 진입점 | `IEventBus` / `IAsyncEventBus` | Outbox seam |
| 실제 메시지 전송 | `IEventTransport` / `IAsyncEventTransport` | Kafka/RabbitMQ |

주요 구현체:

| 구현체 | 역할 |
|--------|------|
| `EventMediator` | Consumer + Dispatcher 통합 (인프로세스) |
| `EventPublisher` | `match event:` 타입 라우터 |
| `DirectEventBus` | 기본 EventBus → Transport 위임 |
| `KafkaEventTransport` | Kafka Transport 구현 |
| `RabbitMQEventTransport` | RabbitMQ Transport 구현 |

### Consumer vs EventHandler

- **Consumer** — 핸들러를 **등록**하는 인터페이스 (`register(event_type, callback)`)
- **EventHandler** — 이벤트를 **처리**하는 클래스 스테레오타입 (`@EventHandler` + `@on_event`)

`EventHandlerRegistrationPostProcessor`가 `@EventHandler` Pod를 스캔하여 `@on_event` 메서드를 Consumer에 자동 등록합니다.

### EventPublisher

이벤트를 발행하는 단일 진입점:

- `IEventPublisher` / `IAsyncEventPublisher` — `publish(event: AbstractEvent)` → 타입 기반 라우팅
  - `AbstractDomainEvent` → `EventMediator` (인프로세스 dispatch)
  - `AbstractIntegrationEvent` → `IEventBus` (외부 전송)

### EventBus / EventTransport

Integration Event 전송을 2단 인터페이스로 분리:

- **EventBus** (`IEventBus`) — Integration Event 발행 진입점. Outbox seam 역할
- **EventTransport** (`IEventTransport`) — 실제 메시지 브로커 전송 (Kafka/RabbitMQ 구현)

---

## 태스크 시스템 (spakky-task)

> 설계 배경은 [ADR-0003](adr/0003-task-schedule-decorator-split.md) 참조.

### @TaskHandler

태스크 핸들러 클래스를 마크하는 스테레오타입. `@task` 및 `@schedule` 메서드를 그룹화합니다.

```python
from spakky.task import TaskHandler, task, schedule
from datetime import timedelta

@TaskHandler()
class EmailTaskHandler:
    @task
    def send_email(self, to: str) -> None: ...

    @schedule(interval=timedelta(hours=1))
    def cleanup(self) -> None: ...
```

### @task

메서드를 온디맨드 디스패치 대상으로 마크하는 데코레이터. 플러그인의 AOP Aspect가 호출을 가로채 태스크 큐로 전달합니다.

### @schedule

메서드를 정기 실행 대상으로 마크하는 데코레이터. `interval`, `at`, `crontab` 중 정확히 하나를 지정해야 합니다.

| 파라미터 | 타입 | 설명 |
|-----------|------|------|
| `interval` | `timedelta` | 고정 간격 실행 |
| `at` | `time` | 매일 특정 시각 실행 |
| `crontab` | `Crontab` | Cron 기반 스케줄 |

### Crontab

Python 네이티브 타입 기반 cron 명세 값 객체. 문자열 대신 `Weekday`/`Month` IntEnum을 사용합니다.

```python
from spakky.task import Crontab, Weekday, Month

# 매주 월요일 09:00
Crontab(weekday=Weekday.MONDAY, hour=9)

# 매년 1월 1일 자정
Crontab(month=Month.JANUARY, day=1)
```

필드 순서: `month` → `day` → `weekday` → `hour` → `minute` (내림차순 시간 척도)

---

## 서비스 생명주기

### IService

시작/종료 생명주기를 가진 동기 서비스 인터페이스.

```python
import threading
from spakky.core.service.interfaces.service import IService

class BackgroundWorker(IService):
    def set_stop_event(self, stop_event: threading.Event) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

### IAsyncService

시작/종료 생명주기를 가진 비동기 서비스 인터페이스.

```python
from asyncio import locks
from spakky.core.service.interfaces.service import IAsyncService

class AsyncWorker(IAsyncService):
    def set_stop_event(self, stop_event: locks.Event) -> None: ...
    async def start_async(self) -> None: ...
    async def stop_async(self) -> None: ...
```

---

## 플러그인 시스템

### Plugin

프레임워크 확장을 식별하는 불변 객체. 이름으로 구분됩니다.

```python
from spakky.core.application.plugin import Plugin

FASTAPI_PLUGIN = Plugin(name="spakky-fastapi")
```

플러그인 로딩:

```python
app.load_plugins(include={FASTAPI_PLUGIN})
```

---

## 데이터 계층 (spakky-data)

### @Transactional

메서드에 트랜잭션 경계를 적용하는 Aspect.

### AggregateCollector

AggregateRoot에서 발생한 도메인 이벤트를 수집하여 트랜잭션 커밋 시 발행하는 컴포넌트.

---

## Transactional Outbox (spakky-outbox)

> 설계 배경은 [ADR-0002](adr/0002-outbox-plugin-architecture.md), [ADR-0006](adr/0006-move-outbox-to-core.md) 참조.

### OutboxEventBus

`@Primary`로 기본 `IEventBus`를 대체하여, Integration Event를 브로커 대신 Outbox 테이블에 저장합니다. 비즈니스 데이터와 같은 트랜잭션 내에서 원자적으로 기록되므로 at-least-once 전달을 보장합니다.

```python
from spakky.outbox.bus.outbox_event_bus import OutboxEventBus, AsyncOutboxEventBus
```

### OutboxMessage

영속성에 독립적인 Outbox 메시지 모델. `id`, `event_name`, `payload`, `headers`, `created_at`, `published_at`, `retry_count`, `claimed_at` 필드를 가집니다.

```python
from spakky.outbox.common.message import OutboxMessage
```

### IOutboxStorage

Outbox 메시지의 CRUD를 담당하는 포트 인터페이스. `spakky-sqlalchemy` 플러그인이 구현체를 제공합니다.

```python
from spakky.outbox.ports.storage import IOutboxStorage, IAsyncOutboxStorage
```

### OutboxRelayBackgroundService

백그라운드 서비스로 Outbox 테이블을 폴링하여 미전송 메시지를 `IEventTransport`로 전송합니다.

---

## 구조화 로깅 (spakky-logging)

### @logged

메서드에 자동 로깅을 적용하는 어노테이션. 인자, 반환값, 실행 시간을 자동 기록합니다. `enable_masking`, `masking_keys`, `slow_threshold_ms`, `max_result_length`, `log_args`, `log_result` 파라미터를 지원합니다.

```python
from spakky.plugins.logging import logged

@logged()
def create_user(self, name: str) -> str: ...
```

### LogContext

`contextvars` 기반 컨텍스트 전파. `bind()`, `unbind()`, `clear()`, `get()`, `scope()` 메서드로 요청 ID 등 공통 정보를 모든 로그에 자동 주입합니다.

```python
from spakky.plugins.logging import LogContext

LogContext.bind(request_id="abc-123")
```

### LoggingConfig

로깅 설정 `@Configuration` Pod. 환경변수 접두사 `SPAKKY_LOGGING__`로 구성합니다. `level`, `format` (`TEXT`/`JSON`/`PRETTY`), `mask_keys`, `slow_threshold_ms` 등을 설정합니다.

---

## 사가 시스템 (spakky-saga)

### @Saga

사가 오케스트레이터 클래스를 마크하는 스테레오타입. `@Pod`의 서브클래스이므로 패키지 스캔만으로 DI 컨테이너에 자동 등록됩니다.

```python
from spakky.saga import AbstractSaga, Saga, SagaFlow, saga_flow, saga_step

@Saga()
class OrderSaga(AbstractSaga[OrderSagaData]):
    @saga_step
    async def create_order(self, data: OrderSagaData) -> OrderSagaData: ...

    def flow(self) -> SagaFlow[OrderSagaData]:
        return saga_flow(self.create_order)
```

### AbstractSaga

사가의 기본 추상 클래스. `flow()`를 구현하여 사가 흐름을 선언하고, `execute(data)`로 실행합니다. 내부적으로 `run_saga_flow`에 클래스명을 `saga_name`으로 전달하여 구조화 로그에 포함합니다.

### @saga_step

사가 step 메서드를 `_SagaStepDescriptor`로 감싸는 데코레이터. 인스턴스 접근 시 bound 메서드가 `SagaStep`으로 승격되어 `>>`, `&`, `|` 연산자가 타입 안전하게 동작합니다.

```python
from spakky.saga import saga_step

@saga_step
async def create_order(self, data: OrderSagaData) -> OrderSagaData: ...
```

### SagaStep / Transaction / Parallel

DSL의 기본 빌딩 블록.

| 타입 | 역할 | 생성 방법 |
|------|------|---------|
| `SagaStep[T]` | 단일 action (compensate 없음) | `step(action)`, `@saga_step` 메서드 |
| `Transaction[T]` | action + compensate 쌍 | `step(action, compensate=...)`, `action >> compensate` |
| `Parallel[T]` | 동시 실행 그룹 (최소 2개) | `parallel(...)`, `a & b` |

### SagaFlow

최상위 흐름 정의. `saga_flow(*items)`로 생성하며, `.timeout(duration)`·`.on_compensation_failure(handler)`로 실행 옵션을 덧붙입니다. `>>` (action + compensate 쌍), `&` (병렬), `|` (에러 전략) 연산자를 지원합니다.

```python
from datetime import timedelta

from spakky.saga import parallel, saga_flow, step

flow = saga_flow(
    step(saga.create_order, compensate=saga.cancel_order),
    parallel(
        step(saga.reserve_stock, compensate=saga.release_stock),
        step(saga.process_payment, compensate=saga.refund_payment),
    ),
).timeout(timedelta(seconds=30))
```

### ErrorStrategy

사가 step 실패 시 적용할 전략:

| 전략 | 설명 |
|------|------|
| `Compensate()` | 역순 보상 후 FAILED 반환 (기본값) |
| `Skip()` | 실패를 무시하고 다음 step으로 진행 |
| `Retry(max_attempts, backoff, then)` | 재시도 후 `then` 전략 적용 |
| `ExponentialBackoff(base=1.0)` | `Retry.backoff`용 지수 백오프 (`base * 2^(attempt-1)`) |

`parallel()` 그룹 내부의 step은 v1에서 기본 `Compensate` 외 `on_error`를 지정할 수 없습니다.

### 타임아웃

| 수준 | 지정 방법 | 동작 |
|------|---------|------|
| step | `step(..., timeout=timedelta(...))` | 초과 시 `SagaStepTimeoutError`가 `on_error` 전략을 거침 |
| saga | `SagaFlow.timeout(duration)` | 초과 시 `SagaStatus.TIMED_OUT`으로 종료하고 commit된 step을 역순 보상 |

### run_saga_flow

`SagaFlow`를 실행하는 얇은 엔트리. `AbstractSaga.execute`가 내부적으로 호출합니다.

```python
from spakky.saga import run_saga_flow

result = await run_saga_flow(flow, data, saga_name="OrderSaga")
```

### SagaResult

사가 실행 결과. `status` (`SagaStatus`), `data`, `failed_step`, `error`, `history` (`tuple[StepRecord, ...]`), `elapsed` 필드를 가집니다. 예외는 발생시키지 않습니다 (보상 실패 시 `SagaCompensationFailedError`는 예외).

### StepRecord / StepStatus

각 step의 실행 기록. `status`는 `COMMITTED` / `FAILED` / `COMPENSATED` 중 하나입니다.

### SagaStatus

사가 전체 상태 열거형: `STARTED`, `RUNNING`, `COMPENSATING`, `COMPLETED`, `FAILED`, `TIMED_OUT`.

### AbstractSagaData

사가 비즈니스 데이터 모델의 기본 클래스. `@immutable` + `AbstractDomainModel`을 확장하며, `saga_id: UUID` 필드가 기본 제공됩니다. 엔진 상태는 포함하지 않습니다.

---

## gRPC 시스템 (spakky-grpc)

### @GrpcController

gRPC 서비스 컨트롤러 클래스를 마크하는 스테레오타입. `@Controller`의 서브클래스입니다.

```python
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController

@GrpcController(package="example.user", service_name="UserService")
class UserServiceController:
    ...
```

### @rpc

메서드를 gRPC RPC 엔드포인트로 마크하는 데코레이터. `RpcMethodType`을 지정하여 스트리밍 모드를 선택할 수 있습니다.

```python
from spakky.plugins.grpc.decorators.rpc import rpc, RpcMethodType

@rpc(method_type=RpcMethodType.UNARY)
async def get_user(self, request: GetUserRequest) -> GetUserResponse:
    ...
```

### RpcMethodType

gRPC 메서드 유형을 나타내는 열거형:

| 값 | 설명 |
|----|------|
| `UNARY` | 단일 요청, 단일 응답 |
| `SERVER_STREAMING` | 단일 요청, 스트림 응답 |
| `CLIENT_STREAMING` | 스트림 요청, 단일 응답 |
| `BIDI_STREAMING` | 양방향 스트리밍 |

### ProtoField

dataclass 필드에 protobuf 메타데이터를 부착하는 어노테이션. code-first protobuf descriptor 생성에 사용됩니다.

```python
from dataclasses import dataclass
from spakky.plugins.grpc.annotations.field import ProtoField

@dataclass
class GetUserRequest:
    user_id: Annotated[str, ProtoField(number=1)]
```

### DescriptorRegistry

protobuf descriptor를 캐싱하고 관리하는 레지스트리. `DescriptorBuilder`가 Python 타입에서 descriptor를 자동 생성합니다. `RegisterServicesPostProcessor`가 `container.get(DescriptorRegistry)`로 조회하므로 사용자가 `@Pod()`으로 반드시 등록해야 합니다.

---

## 분산 트레이싱 (spakky-tracing)

> 설계 배경은 [ADR-0004](adr/0004-distributed-tracing-architecture.md) 참조.

### TraceContext

W3C Trace Context Level 2 호환 컨텍스트 객체. `trace_id`, `span_id`, `parent_span_id`, `trace_flags`를 보유합니다. Python `contextvars`를 사용하여 asyncio 태스크 간 격리됩니다.

```python
from spakky.tracing.context import TraceContext

ctx = TraceContext.new_root()    # 새 트레이스 시작
child = ctx.child()              # 자식 span 생성
TraceContext.set(child)          # 현재 컨텍스트에 설정
TraceContext.get()               # 현재 컨텍스트 조회
TraceContext.clear()             # 컨텍스트 초기화
```

### ITracePropagator

서비스 경계에서 TraceContext를 헤더(carrier)에 주입/추출하는 인터페이스.

| 메서드 | 설명 |
|--------|------|
| `inject(carrier)` | 현재 TraceContext를 carrier에 기록 |
| `extract(carrier)` | carrier에서 TraceContext를 복원 (실패 시 `None`) |
| `fields()` | 사용하는 헤더 필드명 목록 |

### W3CTracePropagator

`ITracePropagator`의 기본 구현체. `traceparent` 헤더를 사용합니다.

### OTelTracePropagator

`ITracePropagator`의 OpenTelemetry 구현체. `spakky-opentelemetry` 플러그인이 로드되면 `OTelSetupPostProcessor`가 기본 `W3CTracePropagator`를 이 구현체로 교체합니다. OpenTelemetry SDK의 `TraceContextTextMapPropagator`에 위임합니다.

```python
from spakky.plugins.opentelemetry.propagator import OTelTracePropagator
```

### OpenTelemetryConfig

`spakky-opentelemetry` 플러그인의 설정 클래스. 환경변수 접두사 `SPAKKY_OTEL_`로 구성합니다.

| 필드 | 환경변수 | 기본값 |
|------|---------|--------|
| `service_name` | `SPAKKY_OTEL_SERVICE_NAME` | `"spakky-service"` |
| `exporter_type` | `SPAKKY_OTEL_EXPORTER_TYPE` | `ExporterType.OTLP` |
| `exporter_endpoint` | `SPAKKY_OTEL_EXPORTER_ENDPOINT` | `"http://localhost:4317"` |
| `sample_rate` | `SPAKKY_OTEL_SAMPLE_RATE` | `1.0` |

### LogContextBridge

`spakky-opentelemetry`의 로깅 통합 컴포넌트. 생성자에서 `ILogContextBinder | None`을 Optional DI로 주입받아, `spakky-logging`이 등록된 경우 `TraceContext`의 trace/span ID를 `LogContext`에 동기화합니다. `ILogContextBinder`가 컨테이너에 없으면 no-op으로 동작합니다.

```python
from spakky.plugins.opentelemetry.bridge import LogContextBridge
```

### traceparent

W3C 표준 분산 트레이싱 헤더. 형식: `{version:2}-{trace_id:32}-{span_id:16}-{flags:2}`

예시: `00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01`

---

## 어노테이션

### @Primary

동일 타입의 여러 Pod 중 기본 선택 대상으로 지정.

```python
@Pod()
@Primary()
class DefaultUserRepository(IUserRepository):
    ...
```

### @Qualifier

의존성 주입 시 특정 Pod를 이름으로 지정.

```python
@Pod(name="cache")
class CacheUserRepository(IUserRepository):
    ...

@Pod()
class UserService:
    def __init__(self, repository: Annotated[IUserRepository, Qualifier(lambda p: p.name == "cache")]) -> None:
        ...
```

### @Lazy

Pod 인스턴스화를 첫 사용 시점까지 지연.

### @Order

Pod 처리 순서를 지정 (숫자가 낮을수록 우선).

### @Tag

Pod를 태그로 그룹화하여 일괄 조회 가능.

---

## 에러 계층

### AbstractSpakkyFrameworkError

모든 Spakky 프레임워크 예외의 기반 클래스.

### PodAnnotationFailedError

Pod 어노테이션 처리 중 발생하는 예외.

### PodInstantiationFailedError

Pod 인스턴스 생성 중 발생하는 예외.
