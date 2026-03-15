# spakky-outbox

Transactional Outbox pattern plugin for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-outbox spakky-sqlalchemy
```

> **Note**: `spakky-outbox` provides the core abstractions; `spakky-sqlalchemy` automatically detects and registers the Outbox storage implementation when both packages are installed.

## Features

- **Transactional Outbox**: Events are saved atomically with business data
- **Automatic relay**: Background relay publishes events to external transports (Kafka, RabbitMQ)
- **Retry support**: Failed messages are retried with configurable limits
- **Multi-instance safe**: Atomic claim prevents duplicate publishing

## Usage

### 1. Load plugins in your application

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()  # Loads outbox and sqlalchemy plugins automatically
    .scan()
    .start()
)
```

### 2. Publish events from use cases

Events published via `IAsyncEventPublisher` are automatically routed:

- `AbstractDomainEvent` → in-process dispatch
- `AbstractIntegrationEvent` → `IEventBus` (Outbox intercepts via `@Primary`)

```python
from spakky.core.common.mutability import immutable
from spakky.core.stereotype.usecase import UseCase
from spakky.data.aspects.transactional import Transactional
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.event_publisher import IAsyncEventPublisher


@immutable
class OrderCreatedEvent(AbstractIntegrationEvent):
    order_id: int
    customer_id: int


@UseCase()
class CreateOrderUseCase:
    def __init__(self, event_publisher: IAsyncEventPublisher) -> None:
        self._event_publisher = event_publisher

    @Transactional()
    async def execute(self, command: CreateOrderCommand) -> Order:
        order = Order.create(...)
        # Event is saved in the same transaction as the order
        await self._event_publisher.publish(
            OrderCreatedEvent(order_id=order.id, customer_id=command.customer_id)
        )
        return order
```

### 3. Configure via environment variables

| Variable                                  | Default | Description                     |
| ----------------------------------------- | ------- | ------------------------------- |
| `SPAKKY_OUTBOX__POLLING_INTERVAL_SECONDS` | `1.0`   | Relay polling interval          |
| `SPAKKY_OUTBOX__BATCH_SIZE`               | `100`   | Messages per batch              |
| `SPAKKY_OUTBOX__MAX_RETRY_COUNT`          | `5`     | Max retries before giving up    |
| `SPAKKY_OUTBOX__CLAIM_TIMEOUT_SECONDS`    | `300.0` | Claim expiry for crash recovery |

## Components

| Component                                                            | Description                                                              |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `IOutboxStorage` / `IAsyncOutboxStorage`                             | Outbox message storage port                                              |
| `OutboxEventBus` / `AsyncOutboxEventBus`                             | Event bus seam for Outbox pattern (`@Primary` replaces `DirectEventBus`) |
| `OutboxRelayBackgroundService` / `AsyncOutboxRelayBackgroundService` | Background relay service (polls & sends)                                 |
| `OutboxConfig`                                                       | Configuration via environment variables                                  |
| `OutboxMessage`                                                      | Outbox message model                                                     |

### Custom Storage Implementation

To implement a custom storage backend:

```python
from spakky.outbox.ports.storage import IAsyncOutboxStorage
from spakky.outbox.common.message import OutboxMessage

class MyCustomStorage(IAsyncOutboxStorage):
    async def save(self, message: OutboxMessage) -> None:
        # Save within the current transaction
        ...

    async def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
        # Atomic claim and return pending messages
        ...

    async def mark_published(self, message_id: UUID) -> None:
        ...

    async def increment_retry(self, message_id: UUID) -> None:
        ...
```

## License

MIT License
