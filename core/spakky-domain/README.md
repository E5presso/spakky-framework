# Spakky DDD

Domain-Driven Design building blocks for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-domain
```

## Features

- **Entities**: Objects with unique identity and lifecycle
- **Value Objects**: Immutable objects compared by attributes
- **Aggregate Roots**: Consistency boundaries with event management
- **Domain Events**: Immutable events for event-driven architecture
- **CQRS**: Command and Query use case abstractions

## Quick Start

### Entity

Entities are objects with a unique identity that persists over time:

```python
from dataclasses import dataclass
from uuid import UUID, uuid4

from spakky.domain.models.entity import AbstractEntity


@dataclass
class User(AbstractEntity[UUID]):
    name: str
    email: str

    @classmethod
    def next_id(cls) -> UUID:
        return uuid4()

    def validate(self) -> None:
        if not self.email:
            raise ValueError("Email is required")
```

### Value Object

Value Objects are immutable and compared by their attributes:

```python
from dataclasses import dataclass

from spakky.domain.models.value_object import AbstractValueObject


@dataclass(frozen=True)
class Money(AbstractValueObject):
    amount: int
    currency: str

    def validate(self) -> None:
        if self.amount < 0:
            raise ValueError("Amount cannot be negative")
```

### Aggregate Root

Aggregate Roots are entities that manage domain events:

```python
from dataclasses import dataclass
from uuid import UUID, uuid4

from spakky.domain.models.aggregate_root import AbstractAggregateRoot
from spakky.domain.models.event import AbstractIntegrationEvent


@dataclass
class OrderCreatedEvent(AbstractIntegrationEvent):
    order_id: UUID
    customer_id: UUID


@dataclass
class Order(AbstractAggregateRoot[UUID]):
    customer_id: UUID
    total: int

    @classmethod
    def next_id(cls) -> UUID:
        return uuid4()

    def validate(self) -> None:
        if self.total < 0:
            raise ValueError("Total cannot be negative")

    @classmethod
    def create(cls, customer_id: UUID, total: int) -> "Order":
        order = cls(uid=cls.next_id(), customer_id=customer_id, total=total)
        order.add_event(OrderCreatedEvent(order_id=order.uid, customer_id=customer_id))
        return order
```

### Domain Events

Domain events represent state changes in the domain:

```python
from dataclasses import dataclass

from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent


# Internal domain event
@dataclass
class UserRegistered(AbstractDomainEvent):
    user_id: str
    email: str


# Cross-boundary integration event
@dataclass
class UserRegisteredIntegration(AbstractIntegrationEvent):
    user_id: str
    email: str
```

### CQRS Use Cases

Separate read and write operations:

```python
from dataclasses import dataclass
from uuid import UUID

from spakky.domain.application.command import AbstractCommand, IAsyncCommandUseCase
from spakky.domain.application.query import AbstractQuery, IAsyncQueryUseCase


# Command
@dataclass
class CreateUserCommand(AbstractCommand):
    name: str
    email: str


class CreateUserUseCase(IAsyncCommandUseCase[CreateUserCommand, UUID]):
    async def execute(self, command: CreateUserCommand) -> UUID:
        # Business logic here
        ...


# Query
@dataclass
class GetUserQuery(AbstractQuery):
    user_id: UUID


class GetUserUseCase(IAsyncQueryUseCase[GetUserQuery, User | None]):
    async def execute(self, query: GetUserQuery) -> User | None:
        # Business logic here
        ...
```

## API Reference

### Models

| Class                      | Description                                    |
| -------------------------- | ---------------------------------------------- |
| `AbstractEntity[T]`        | Base class for entities with identity type `T` |
| `AbstractAggregateRoot[T]` | Entity that manages domain events              |
| `AbstractValueObject`      | Immutable value object                         |
| `AbstractDomainEvent`      | Base class for domain events                   |
| `AbstractIntegrationEvent` | Events for cross-boundary communication        |

### Application

| Class                  | Description                      |
| ---------------------- | -------------------------------- |
| `AbstractCommand`      | Base class for command DTOs      |
| `AbstractQuery`        | Base class for query DTOs        |
| `ICommandUseCase`      | Sync command use case interface  |
| `IAsyncCommandUseCase` | Async command use case interface |
| `IQueryUseCase`        | Sync query use case interface    |
| `IAsyncQueryUseCase`   | Async query use case interface   |

## Related Packages

| Package | Description |
|---------|-------------|
| `spakky-data` | Repository and transaction abstractions |
| `spakky-event` | Event publisher/consumer interfaces and `@EventHandler` stereotype |

## License

MIT License
