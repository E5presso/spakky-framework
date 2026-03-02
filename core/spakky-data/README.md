# Spakky Data

Data access layer abstractions for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-data
```

## Features

- **Repository Pattern**: Generic repository interfaces for aggregate persistence
- **Transaction Management**: Abstract transaction classes with autocommit support
- **External Proxy**: Proxy pattern for **external service/storage** data access (NOT for database)

## Design Principles

### Repository is for Persistence Only

Repositories handle **CRUD operations for domain aggregates only**.
Do NOT add query methods like `find_by_xxx`, `search_xxx` to repositories.

Complex queries should be implemented directly in **QueryUseCase** using ORM/SQL.
This prevents domain pollution by keeping query concerns out of the domain layer.

```python
# ❌ Wrong: Query concerns in repository
class IUserRepository:
    def find_by_email(self, email: str) -> User | None: ...

# ✅ Correct: Direct implementation in QueryUseCase
@QueryUseCase()
class FindUserByEmailUseCase(IAsyncQueryUseCase[FindUserByEmailQuery, UserDTO]):
    async def run(self, query: FindUserByEmailQuery) -> UserDTO:
        # Use ORM/SQL directly
        ...
```

### External Proxy vs Repository

| Aspect | Repository | External Proxy |
|--------|-----------|----------------|
| Purpose | Domain aggregate persistence | External service data access |
| Target | Database (via ORM) | REST API, gRPC, legacy systems |
| Operations | CRUD (save, delete, get) | Read-only (get, range) |
| Domain | Internal bounded context | External services |

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


# Repository interface - CRUD only, no query methods
class IUserRepository(IAsyncGenericRepository[User, UUID]):
    pass  # get, get_or_none, contains, range, save, save_all, delete, delete_all
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

Access **external services** (NOT databases) with proxy interfaces.
Use this for REST APIs, gRPC services, legacy systems, etc.

```python
from spakky.data.external.proxy import ProxyModel, IAsyncGenericProxy


# Data model from external payment service
class PaymentInfo(ProxyModel[str]):
    transaction_id: str
    amount: int
    status: str


# Proxy interface for external payment service
class IPaymentProxy(IAsyncGenericProxy[PaymentInfo, str]):
    pass


# Implementation calls external API
class PaymentServiceProxy(IPaymentProxy):
    async def get(self, proxy_id: str) -> PaymentInfo:
        response = await self._http_client.get(f"/payments/{proxy_id}")
        return PaymentInfo(...)
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
