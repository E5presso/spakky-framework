# spakky-outbox

Transactional Outbox pattern plugin for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-outbox spakky-outbox-sqlalchemy
```

> **Note**: `spakky-outbox` provides the core abstractions; you must also install a storage implementation like `spakky-outbox-sqlalchemy`.

## Features

- **Transactional Outbox**: Events are saved atomically with business data
- **Automatic relay**: Background relay publishes events to external transports (Kafka, RabbitMQ)
- **Retry support**: Failed messages are retried with configurable limits
- **Multi-instance safe**: Atomic claim prevents duplicate publishing

## Usage

### 1. Load plugins in your application

```python
from spakky import Spakky
from spakky.plugins.outbox import initialize as outbox_init
from spakky.plugins.outbox_sqlalchemy import initialize as outbox_sqlalchemy_init

app = Spakky(...)

# Load outbox plugins (order matters)
outbox_init(app)
outbox_sqlalchemy_init(app)
```

### 2. Publish events from use cases

```python
from spakky.data.transaction import transaction
from spakky.domain.models.event import AbstractIntegrationEvent

class OrderCreatedEvent(AbstractIntegrationEvent):
    order_id: int
    customer_id: int

class CreateOrderUseCase:
    _event_publisher: AsyncEventPublisher

    def __init__(self, event_publisher: AsyncEventPublisher) -> None:
        self._event_publisher = event_publisher

    @transaction
    async def execute(self, command: CreateOrderCommand) -> Order:
        order = Order.create(...)
        # Event is saved in the same transaction as the order
        await self._event_publisher.publish(OrderCreatedEvent(order_id=order.id, ...))
        return order
```

### 3. Configure via environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SPAKKY_OUTBOX__POLLING_INTERVAL_SECONDS` | `1.0` | Relay polling interval |
| `SPAKKY_OUTBOX__BATCH_SIZE` | `100` | Messages per batch |
| `SPAKKY_OUTBOX__MAX_RETRY_COUNT` | `5` | Max retries before giving up |
| `SPAKKY_OUTBOX__CLAIM_TIMEOUT_SECONDS` | `300.0` | Claim expiry for crash recovery |

## Custom Storage Implementation

To implement a custom storage backend:

```python
from spakky.plugins.outbox.ports.storage import IAsyncOutboxStorage
from spakky.plugins.outbox.common.message import OutboxMessage

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
