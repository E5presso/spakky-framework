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
from spakky.domain.models.event import AbstractDomainEvent
from spakky.domain.ports.event.event_publisher import IEventPublisher
from spakky.pod.annotations.pod import Pod

class UserCreatedEvent(AbstractDomainEvent):
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
from spakky.stereotype.event_handler import EventHandler, on_event

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
from spakky.domain.ports.event.event_publisher import IAsyncEventPublisher

@Pod()
class AsyncUserService:
    def __init__(self, publisher: IAsyncEventPublisher) -> None:
        self.publisher = publisher

    async def create_user(self, email: str) -> User:
        user = User(email=email)
        await self.publisher.publish(UserCreatedEvent(user_id=user.id, email=email))
        return user
```

## Features

- **Automatic queue declaration**: Queues are created based on event type names
- **Sync and Async support**: Both synchronous and asynchronous publishers/consumers
- **Background service pattern**: Consumer polling runs as a background service
- **Pydantic serialization**: Events are serialized/deserialized using Pydantic
- **Exchange routing**: Optional exchange for pub/sub message patterns
- **SSL support**: Secure connections via AMQPS protocol

## Components

| Component | Description |
|-----------|-------------|
| `RabbitMQEventPublisher` | Synchronous event publisher |
| `AsyncRabbitMQEventPublisher` | Asynchronous event publisher |
| `RabbitMQEventConsumer` | Synchronous event consumer (background service) |
| `AsyncRabbitMQEventConsumer` | Asynchronous event consumer (background service) |
| `RabbitMQConnectionConfig` | Configuration via environment variables |

## Error Handling

- **`DuplicateEventHandlerError`**: Raised when multiple handlers are registered for the same event type
- **`InvalidMessageError`**: Raised when a message is missing required metadata (`consumer_tag` or `delivery_tag`)

## License

MIT License
