# Spakky SQLAlchemy

SQLAlchemy integration plugin for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-sqlalchemy
```

Or install via Spakky extras:

```bash
pip install spakky[sqlalchemy]
```

## Configuration

Set environment variables with the `SPAKKY_SQLALCHEMY__` prefix:

```bash
# Required
export SPAKKY_SQLALCHEMY__CONNECTION_STRING="postgresql+psycopg://user:pass@localhost/db"

# Engine options (optional)
export SPAKKY_SQLALCHEMY__ECHO="false"
export SPAKKY_SQLALCHEMY__ECHO_POOL="false"

# Connection pool options (optional)
export SPAKKY_SQLALCHEMY__POOL_SIZE="5"
export SPAKKY_SQLALCHEMY__POOL_MAX_OVERFLOW="10"
export SPAKKY_SQLALCHEMY__POOL_TIMEOUT="30.0"
export SPAKKY_SQLALCHEMY__POOL_RECYCLE="-1"
export SPAKKY_SQLALCHEMY__POOL_PRE_PING="false"

# Session options (optional)
export SPAKKY_SQLALCHEMY__SESSION_AUTOFLUSH="true"
export SPAKKY_SQLALCHEMY__SESSION_EXPIRE_ON_COMMIT="true"

# Transaction options (optional)
export SPAKKY_SQLALCHEMY__AUTOCOMMIT="true"

# Async support (optional)
export SPAKKY_SQLALCHEMY__SUPPORT_ASYNC_MODE="true"
```

## Usage

### Defining Tables with Domain Mapping

Use `@Table` decorator and inherit from `AbstractTable` to define ORM tables with domain model mapping:

```python
from uuid import UUID
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from spakky.plugins.sqlalchemy.orm.table import AbstractTable, Table
from spakky.domain.models.aggregate_root import AbstractAggregateRoot

# Domain model
class User(AbstractAggregateRoot[UUID]):
    id: UUID
    name: str
    email: str

# Table definition with domain mapping
@Table()
class UserTable(AbstractMappableTable[User]):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))

    @classmethod
    def from_domain(cls, domain: User) -> "UserTable":
        return cls(id=domain.id, name=domain.name, email=domain.email)

    def to_domain(self) -> User:
        return User(id=self.id, name=self.name, email=self.email)
```

### Repository Implementation

Extend `AbstractGenericRepository` or `AbstractAsyncGenericRepository`:

```python
from uuid import UUID
from spakky.data.stereotype.repository import Repository
from spakky.plugins.sqlalchemy.persistency.repository import (
    AbstractGenericRepository,
    AbstractAsyncGenericRepository,
)

# Synchronous repository
@Repository()
class UserRepository(AbstractGenericRepository[User, UUID]):
    pass  # CRUD methods inherited

# Asynchronous repository
@Repository()
class AsyncUserRepository(AbstractAsyncGenericRepository[User, UUID]):
    pass  # Async CRUD methods inherited
```

### Using Transactions

Use the `@Transactional` decorator from `spakky-data`:

```python
from spakky.core.stereotype.usecase import UseCase
from spakky.data.aspects.transactional import Transactional

@UseCase()
class CreateUserUseCase:
    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo

    @Transactional()
    def execute(self, name: str, email: str) -> User:
        user = User.create(name, email)
        return self._user_repo.save(user)
```

### Async Transactions

The same `@Transactional()` decorator works for both sync and async methods.
The framework automatically selects the correct aspect based on whether the method is a coroutine.

```python
from spakky.data.aspects.transactional import Transactional

@UseCase()
class AsyncCreateUserUseCase:
    def __init__(self, user_repo: AsyncUserRepository) -> None:
        self._user_repo = user_repo

    @Transactional()
    async def execute(self, name: str, email: str) -> User:
        user = User.create(name, email)
        return await self._user_repo.save(user)
```

### Accessing Session Directly

For complex queries, access the SQLAlchemy session directly in **QueryUseCase**.
Following CQRS principles, queries should be implemented directly rather than
adding query methods to repositories.

```python
from spakky.core.common.mutability import immutable
from spakky.core.stereotype.usecase import UseCase
from spakky.domain.application.query import AbstractQuery, IAsyncQueryUseCase
from spakky.plugins.sqlalchemy.persistency.session_manager import AsyncSessionManager


@immutable
class FindUserByEmailQuery(AbstractQuery):
    email: str


@immutable
class UserDTO:
    id: UUID
    name: str
    email: str


@UseCase()
class FindUserByEmailUseCase(IAsyncQueryUseCase[FindUserByEmailQuery, UserDTO | None]):
    def __init__(self, session_manager: AsyncSessionManager) -> None:
        self._session_manager = session_manager

    async def run(self, query: FindUserByEmailQuery) -> UserDTO | None:
        result = await self._session_manager.session.execute(
            select(UserTable).where(UserTable.email == query.email)
        )
        table = result.scalar_one_or_none()
        if table is None:
            return None
        return UserDTO(id=table.id, name=table.name, email=table.email)
```

### Schema Registry

Access `SchemaRegistry` to get table metadata for migrations:

```python
from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry

@Pod()
class MigrationService:
    def __init__(self, schema_registry: SchemaRegistry) -> None:
        self._schema_registry = schema_registry

    def get_metadata(self) -> MetaData:
        return self._schema_registry.metadata
```

## Features

- **Domain-Table mapping**: Bidirectional conversion between domain models and ORM tables
- **Generic repositories**: Pre-built CRUD operations with composite PK support
- **Sync and Async support**: Full support for both synchronous and asynchronous operations
- **Scoped sessions**: Thread/context-safe session management
- **Optimistic locking**: Built-in `VersionConflictError` for concurrent updates
- **Schema registry**: Centralized table metadata management

## Components

| Component | Description |
|-----------|-------------|
| `@Table` | Decorator for registering ORM tables with domain mapping |
| `AbstractTable` | Base class for ORM tables with `from_domain`/`to_domain` |
| `AbstractGenericRepository` | Sync repository with CRUD operations |
| `AbstractAsyncGenericRepository` | Async repository with CRUD operations |
| `SchemaRegistry` | Central registry for table-domain mappings |
| `SessionManager` | Sync scoped session management |
| `AsyncSessionManager` | Async scoped session management |
| `Transaction` | Sync transaction implementation |
| `AsyncTransaction` | Async transaction implementation |
| `ConnectionManager` | Sync SQLAlchemy engine lifecycle |
| `AsyncConnectionManager` | Async SQLAlchemy engine lifecycle |
| `SQLAlchemyConnectionConfig` | Configuration via environment variables |

## Repository Methods

Both sync and async repositories provide:

| Method | Description |
|--------|-------------|
| `get(id)` | Get aggregate by ID, raises `EntityNotFoundError` if not found |
| `get_or_none(id)` | Get aggregate by ID, returns `None` if not found |
| `contains(id)` | Check if aggregate exists |
| `range(ids)` | Get multiple aggregates by ID list |
| `save(aggregate)` | Save (insert or update) an aggregate |
| `save_all(aggregates)` | Save multiple aggregates |
| `delete(aggregate)` | Delete an aggregate |
| `delete_all(aggregates)` | Delete multiple aggregates |

## License

MIT License
