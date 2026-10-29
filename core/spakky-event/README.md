# Spakky Event

> [Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 이벤트 처리 stereotype입니다.

## 설치

```bash
pip install spakky-event
```

## 주요 기능

- **`@EventHandler`**: 이벤트 handler 클래스용 stereotype
- **`@on_event`**: 메서드를 이벤트 handler로 표시하는 decorator
- **타입 안전성**: 이벤트 타입에 대한 타입 힌트 지원
- **비동기 지원**: 이벤트 처리에 async/await 네이티브 지원

## 빠른 시작

### 이벤트 정의

이벤트는 `spakky-domain`의 이벤트 기반 클래스 중 하나를 상속해야 합니다.

- bounded context 내부 이벤트(in-process domain event)에는 `AbstractDomainEvent`를 사용합니다.
- 경계를 넘는 이벤트(message broker integration)에는 `AbstractIntegrationEvent`를 사용합니다.

메시지 브로커 플러그인(RabbitMQ/Kafka)을 사용할 때는 이벤트를 `AbstractIntegrationEvent`로 정의하세요.

```python
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent


@immutable
class UserCreatedEvent(AbstractIntegrationEvent):
    user_id: str
    email: str


@immutable
class UserDeletedEvent(AbstractIntegrationEvent):
    user_id: str
```

### EventHandler 생성

`@EventHandler` stereotype과 `@on_event` decorator를 함께 사용합니다.

```python
from spakky.event.stereotype.event_handler import EventHandler, on_event


@EventHandler()
class UserEventHandler:
    def __init__(self, notification_service: NotificationService) -> None:
        self.notification_service = notification_service

    @on_event(UserCreatedEvent)
    async def on_user_created(self, event: UserCreatedEvent) -> None:
        await self.notification_service.send_welcome_email(event.email)

    @on_event(UserDeletedEvent)
    async def on_user_deleted(self, event: UserDeletedEvent) -> None:
        await self.notification_service.send_goodbye_email(event.user_id)
```

### 메시지 브로커 통합

`@EventHandler` stereotype은 Spakky의 message broker 플러그인과 함께 동작합니다.

#### RabbitMQ

```bash
pip install spakky-rabbitmq
```

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()  # Loads spakky-rabbitmq plugin
    .scan()
    .start()
)
```

#### Kafka

```bash
pip install spakky-kafka
```

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()  # Loads spakky-kafka plugin
    .scan()
    .start()
)
```

## API 레퍼런스

### 스테레오타입

| 데코레이터 | 설명 |
|-----------|-------------|
| `@EventHandler()` | 클래스를 event handler로 표시(`@Pod` 확장) |
| `@on_event(EventType)` | 메서드를 특정 event type의 handler로 표시 |

### 인터페이스

| 인터페이스 | 설명 |
|-----------|-------------|
| `IEventPublisher` / `IAsyncEventPublisher` | Event publish 진입점(type-based routing) |
| `IEventBus` / `IAsyncEventBus` | Integration event send 진입점(Outbox 경계) |
| `IEventTransport` / `IAsyncEventTransport` | 실제 message broker transport. `send`로 payload를 넘기고, 배치 끝에서 `flush`로 전송을 확정합니다. 영구적이고 특정 레코드에 귀속되는 거부만 `EventDeliveryRejectedError`로 통일하며, connection·timeout·queue 등 transport 전체 장애는 client 예외 타입을 보존합니다. 애플리케이션 수명 밖의 발행은 `EventTransportNotRunningError`로 거부됩니다 |
| `IEventConsumer` / `IAsyncEventConsumer` | Handler callback 등록 |
| `IEventDispatcher` / `IAsyncEventDispatcher` | In-process handler dispatch |

### 구현체

| 클래스 | 설명 |
|-------|-------------|
| `EventMediator` / `AsyncEventMediator` | 별도 `spakky-mediator` 플러그인이 제공하는 in-process Consumer/Dispatcher |
| `EventPublisher` / `AsyncEventPublisher` | Type-based router(DomainEvent→Mediator, IntegrationEvent→EventBus) |
| `DirectEventBus` / `AsyncDirectEventBus` | 기본 EventBus → EventTransport 위임 구현 |
| `AuthContextSnapshotHeaderInjector` | Event/Outbox outbound header에 signed `AuthContextSnapshot` metadata를 주입하는 helper |
| `EventHandlerRegistrationPostProcessor` | 별도 `spakky-mediator` 플러그인이 domain handler를 자동 등록 |

### 전파 metadata

`DirectEventBus`와 `AsyncDirectEventBus`는 `IEventTransport.send(event_name, payload, headers, partition_key)` public signature로 outbound header를 구성하고, 이벤트가 선언한 partition key를 그대로 넘깁니다. 직접 발행은 1건 배치이므로 두 bus는 `send` 직후 `flush`를 호출하여 전송을 확정한 뒤 반환합니다.

| metadata | 조건 | 설명 |
|----------|------|------|
| `traceparent` | `spakky-tracing` propagator 활성 | 기존 W3C tracing header를 보존합니다. |
| `spakky.auth.context_snapshot` | `SPAKKY_AUTH_SNAPSHOT_PROPAGATION_ENABLED=true` + request-scope `AuthContext` + snapshot signer provider | raw bearer token 대신 signed `AuthContextSnapshot` envelope를 전파합니다. |

`Authorization: Bearer ...` 같은 raw bearer credential은 event header로 전파하지 않습니다.

### 타입

| 타입 | 설명 |
|------|-------------|
| `EventRoute` | event routing metadata용 annotation 클래스 |
| `EventT_contra` | `AbstractEvent`에 bound된 TypeVar |
| `EventHandlerCallback` | 동기 event callback용 type alias |
| `AsyncEventHandlerCallback` | 비동기 event callback용 type alias |

### 에러

| 클래스 | 설명 |
|-------|-------------|
| `AbstractSpakkyEventError` | event operation 기반 error |
| `AuthSnapshotPropagationContextUnavailableError` | snapshot 전파가 활성화되었지만 `ApplicationContext`를 읽을 수 없을 때 발생 |
| `AuthSnapshotPropagationSignerUnavailableError` | snapshot 전파가 활성화되었지만 signer provider가 없을 때 발생 |
| `InvalidMessageError` | message가 malformed일 때 발생 |

## 관련 패키지

| 패키지 | 설명 |
|---------|-------------|
| `spakky-domain` | DDD building block 포함 `AbstractEvent`, `AbstractDomainEvent`, `AbstractIntegrationEvent` |
| `spakky-rabbitmq` | RabbitMQ transport(`RabbitMQEventTransport`) |
| `spakky-kafka` | Kafka transport(`KafkaEventTransport`) |

## In-process 도메인 이벤트 발행

bounded context 내부 이벤트(DomainEvents)에는 in-process publisher를 사용합니다.

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.event import IAsyncEventPublisher

# 애플리케이션 부트스트랩(load_plugins가 event component를 자동 등록)
app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()
    .scan()
    .start()
)

# 컨테이너에서 publisher 조회
publisher = app.container.get(IAsyncEventPublisher)
await publisher.publish(UserCreatedEvent(user_id="123", email="test@example.com"))
```

### 아키텍처(ISP 준수)

in-process event system은 Interface Segregation Principle을 따릅니다.

- **Consumer**: event handler 등록(`register()` 메서드)
- **Dispatcher**: event를 handler로 dispatch(`dispatch()` 메서드)
- **Mediator**: 두 인터페이스를 단일 구현체로 결합
- **Publisher**: Consumer가 아니라 Dispatcher에만 의존

```mermaid
flowchart TD
    publisher[Publisher]
    dispatcher[Dispatcher]
    mediator["Mediator<br/>Consumer + Dispatcher"]
    handler["EventHandler<br/>@on_event"]

    publisher --> dispatcher
    dispatcher --> mediator
    mediator --> handler
```

## 개발 검증

패키지 단위 검증은 해당 패키지 디렉토리에서 실행합니다.

```bash
uv run ruff format .
uv run ruff check .
uv run pyrefly check
uv run pytest
```

`pytest`는 각 패키지 `pyproject.toml`의 coverage 설정을 사용합니다.

## 라이선스

MIT License

### 인프로세스 이벤트와 후속 작업

Domain Event만 사용하는 앱은 외부 transport 없이 기동할 수 있습니다. Integration Event를 발행할 때는 실제 transport 플러그인이 필요하며, 없으면 `IntegrationEventTransportUnavailableError`가 발생합니다.

트랜잭션 이벤트 Aspect는 커밋과 세션 정리가 끝난 뒤 이벤트를 발행합니다. 발행할 배치와 collector를 먼저 분리하므로 핸들러가 새 `@transactional` 유스케이스를 호출해도 부모 이벤트를 재발행하지 않습니다. 커밋 실패 시 이벤트는 발행하지 않습니다. 인프로세스 이벤트는 영속 메시지 큐를 대신하지 않습니다.

## 명시적인 이벤트 제공자 선택

`spakky-event`는 이벤트 계약·발행·Aspect와 제공자 검증을 소유합니다. 로컬 domain
consumer/dispatcher는 별도 `spakky-mediator` 플러그인을 설치하고 선택해야 합니다.
Kafka/RabbitMQ만 사용하는 서비스에는 로컬 mediator가 자동으로 등록되지 않습니다.
`spakky[event]`도 mediator를 숨겨 설치하지 않습니다.

| 구성 | 가능한 동작 |
| --- | --- |
| event | 계약과 발행 진입점; 없는 제공자로의 발행은 명시적 오류 |
| event + mediator | 동기·비동기 domain event 등록과 로컬 dispatch |
| event + Kafka | 동기·비동기 integration event 발행·소비 |
| event + mediator + Kafka | 두 이벤트 종류가 각 제공자로 독립적으로 전달됨 |

선언한 handler의 동기/비동기 및 domain/integration 역할에 맞는 consumer가 없으면
`EventHandlerProviderUnavailableError`로 기동을 실패시킵니다. domain 발행에 dispatcher가
없으면 `DomainEventDispatcherUnavailableError`, integration 발행에 transport가 없으면
`IntegrationEventTransportUnavailableError`를 발생시킵니다. 누락된 이벤트를 조용히 버리지 않습니다.

구현 import 이전과 설치 예시는 [Mediator API](../../plugins/spakky-mediator/README.md)를 참고하세요.



### Transport 플러그인과 handler 등록

`spakky-mediator`의 `EventHandlerRegistrationPostProcessor`는 domain event handler를
자신의 `EventMediator`/`AsyncEventMediator`에 등록합니다. core는 제공자만 검증합니다. Kafka 등의 transport consumer가
같은 컨테이너에 있어도 generic consumer 포트의 구현 후보와 충돌하지 않으며,
integration handler의 등록은 해당 transport 플러그인의 post-processor가 소유합니다.

### 소비 유예 계약

`from spakky.event import EventDeferredError`로 효과를 만들기 전의 일시적 처리 유예를
표현합니다. `EventDeferredError(retry_after=1.0)`의 지연은 유한한 양수 초이며 잘못된
값은 `InvalidEventDeferralError`입니다. handler의 트랜잭션은 예외가 consumer에
도달하기 전에 rollback되어야 합니다. 앞서 실행된 handler는 멱등이어야 합니다.

지원하는 broker consumer는 이를 업무 실패/DLT와 구분하고 commit 없이 재전달합니다.
현재 Kafka plugin은 partition pause/rewind와 지속적인 poll로 이 계약을 구현합니다.
직접 in-process event dispatch는 broker 재전달을 만들지 않고 호출자에게 예외를
전파합니다. 유예가 이미 시작한 handler의 장기 작업을 취소하는 기능은 아닙니다.
