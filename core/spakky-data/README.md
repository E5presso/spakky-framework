# Spakky Data

Data access layer abstractions for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-data
```

## Features

- **Repository Pattern**: Generic repository interfaces for aggregate persistence
- **Transaction Management**: Abstract transaction classes with autocommit support
- **External Proxy**: Proxy pattern for external service data access

## Quick Start

### Repository Pattern

Define repository interfaces for your domain aggregates:

```python
from abc import abstractmethod
from uuid import UUID

from spakky.data.persistency.repository import IAsyncGenericRepository
from spakky.domain.models.aggregate_root import AbstractAggregateRoot


class User(AbstractAggregateRoot[UUID]):
    name: str
    email: str


class IUserRepository(IAsyncGenericRepository[User, UUID]):
    @abstractmethod
    async def find_by_email(self, email: str) -> User | None: ...
```

### Transaction Management

Use abstract transactions for database operations:

```python
from spakky.data.persistency.transaction import AbstractAsyncTransaction


class SQLAlchemyTransaction(AbstractAsyncTransaction):
    def __init__(self, session_factory, autocommit: bool = True) -> None:
        super().__init__(autocommit)
        self.session_factory = session_factory
        self.session = None

    async def initialize(self) -> None:
        self.session = self.session_factory()

    async def dispose(self) -> None:
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
```

Usage with context manager:

```python
async with transaction:
    user = await repository.get(user_id)
    user.name = "New Name"
    await repository.save(user)
    # Automatically commits on success, rollbacks on exception
```

### External Proxy Pattern

Access external service data with proxy interfaces:

```python
from spakky.data.external.proxy import ProxyModel, IAsyncGenericProxy


class ExternalUser(ProxyModel[int]):
    name: str
    email: str


class IExternalUserProxy(IAsyncGenericProxy[ExternalUser, int]):
    pass
```

## API Reference

### Persistency

| Class | Description |
|-------|-------------|
| `IGenericRepository` | Sync generic repository interface |
| `IAsyncGenericRepository` | Async generic repository interface |
| `AbstractTransaction` | Sync transaction with context manager |
| `AbstractAsyncTransaction` | Async transaction with context manager |
| `EntityNotFoundError` | Raised when entity not found |

### External

| Class | Description |
|-------|-------------|
| `ProxyModel` | Base class for external service data models |
| `IGenericProxy` | Sync proxy interface |
| `IAsyncGenericProxy` | Async proxy interface |

### Errors

| Class | Description |
|-------|-------------|
| `AbstractSpakkyPersistencyError` | Base error for persistency operations |
| `AbstractSpakkyExternalError` | Base error for external service operations |

## Related Packages

| Package | Description |
|---------|-------------|
| `spakky-domain` | DDD building blocks (Entity, AggregateRoot, ValueObject) |
| `spakky-event` | Event publisher/consumer interfaces |

## License

MIT License
