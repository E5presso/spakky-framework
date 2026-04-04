# Spakky RabbitMQ

RabbitMQ plugin for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-rabbitmq
```

Or install via Spakky extras:

```bash
pip install spakky[rabbitmq]
```

## Configuration

Set environment variables with the `SPAKKY_RABBITMQ__` prefix:

```bash
export SPAKKY_RABBITMQ__USE_SSL="false"
export SPAKKY_RABBITMQ__HOST="localhost"
export SPAKKY_RABBITMQ__PORT="5672"
export SPAKKY_RABBITMQ__USER="guest"
export SPAKKY_RABBITMQ__PASSWORD="guest"
export SPAKKY_RABBITMQ__EXCHANGE_NAME="my-exchange"  # Optional
```

## Usage

### Event Publishing

```python
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.event_publisher import IEventPublisher
from spakky.core.pod.annotations.pod import Pod

@immutable
class UserCreatedEvent(AbstractIntegrationEvent):
    user_id: int
    email: str

@Pod()
class UserService:
    def __init__(self, publisher: IEventPublisher) -> None:
        self.publisher = publisher

    def create_user(self, email: str) -> User:
        user = User(email=email)
        self.publisher.publish(UserCreatedEvent(user_id=user.id, email=email))
        return user
```

### Event Consuming

```python
from spakky.event.stereotype.event_handler import EventHandler, on_event

@EventHandler()
class UserEventHandler:
    def __init__(self, notification_service: NotificationService) -> None:
        self.notification_service = notification_service

    @on_event(UserCreatedEvent)
    async def on_user_created(self, event: UserCreatedEvent) -> None:
        await self.notification_service.send_welcome_email(event.email)
```

### Async Variants

For async applications, use `IAsyncEventPublisher`:

```python
from spakky.event.event_publisher import IAsyncEventPublisher

@Pod()
class AsyncUserService:
    def __init__(self, publisher: IAsyncEventPublisher) -> None:
        self.publisher = publisher

    async def create_user(self, email: str) -> User:
        user = User(email=email)
        await self.publisher.publish(UserCreatedEvent(user_id=user.id, email=email))
        return user
```

## Distributed Tracing

`spakky-tracing`은 필수 의존성으로 자동 설치됩니다. `ITracePropagator`가 컨테이너에 등록되어 있으면 이벤트 발행/소비 시 `TraceContext`가 자동으로 전파됩니다.

- **발행 측**: `IEventTransport.send()` 시 현재 `TraceContext`를 메시지 헤더에 주입합니다
- **소비 측**: 수신 메시지에서 `TraceContext`를 추출하여 자식 스팬을 생성합니다
- 헤더가 없으면 새로운 루트 트레이스를 시작합니다

## Features

- **Automatic queue declaration**: Queues are created based on event type names
- **Sync and Async support**: Both synchronous and asynchronous publishers/consumers
- **Background service pattern**: Consumer polling runs as a background service
- **Pydantic serialization**: Events are serialized/deserialized using Pydantic
- **Exchange routing**: Optional exchange for pub/sub message patterns
- **SSL support**: Secure connections via AMQPS protocol
- **Distributed tracing**: `spakky-tracing` integration for cross-service trace propagation

## Components

| Component | Description |
|-----------|-------------|
| `RabbitMQEventTransport` | Synchronous event transport (`IEventTransport`) |
| `AsyncRabbitMQEventTransport` | Asynchronous event transport (`IAsyncEventTransport`) |
| `RabbitMQEventConsumer` | Synchronous event consumer (background service) |
| `AsyncRabbitMQEventConsumer` | Asynchronous event consumer (background service) |
| `RabbitMQConnectionConfig` | Configuration via environment variables |

## Error Handling

- **`InvalidMessageError`**: Raised when a message is missing required metadata (`consumer_tag` or `delivery_tag`)

## License

MIT License
