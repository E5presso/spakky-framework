# Spakky Kafka

Apache Kafka plugin for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-kafka
```

Or install via Spakky extras:

```bash
pip install spakky[kafka]
```

## Configuration

Set environment variables with the `SPAKKY_KAFKA__` prefix:

```bash
export SPAKKY_KAFKA__GROUP_ID="my-consumer-group"
export SPAKKY_KAFKA__CLIENT_ID="my-app"
export SPAKKY_KAFKA__BOOTSTRAP_SERVERS="localhost:9092"
export SPAKKY_KAFKA__AUTO_OFFSET_RESET="earliest"  # earliest, latest, none
```

### SASL Authentication (Optional)

```bash
export SPAKKY_KAFKA__SECURITY_PROTOCOL="SASL_SSL"
export SPAKKY_KAFKA__SASL_MECHANISM="PLAIN"
export SPAKKY_KAFKA__SASL_USERNAME="username"
export SPAKKY_KAFKA__SASL_PASSWORD="password"
```

### Topic Configuration (Optional)

```bash
export SPAKKY_KAFKA__NUMBER_OF_PARTITIONS="3"
export SPAKKY_KAFKA__REPLICATION_FACTOR="1"
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

- **Automatic topic creation**: Topics are created based on event type names
- **Sync and Async support**: Both synchronous and asynchronous publishers/consumers
- **Background service pattern**: Consumer polling runs as a background service
- **Pydantic serialization**: Events are serialized/deserialized using Pydantic
- **Confluent Kafka client**: Built on the robust `confluent-kafka` library

## Components

| Component | Description |
|-----------|-------------|
| `KafkaEventPublisher` | Synchronous event publisher |
| `AsyncKafkaEventPublisher` | Asynchronous event publisher |
| `KafkaEventConsumer` | Synchronous event consumer (background service) |
| `AsyncKafkaEventConsumer` | Asynchronous event consumer (background service) |
| `KafkaConnectionConfig` | Configuration via environment variables |

## License

MIT License
