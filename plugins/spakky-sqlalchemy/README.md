# Spakky SQLAlchemy

[Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 SQLAlchemy 통합 플러그인입니다.

## 설치

```bash
pip install spakky-sqlalchemy
```

Spakky extras로도 설치할 수 있습니다.

```bash
pip install spakky[sqlalchemy]
```

## 설정

`SPAKKY_SQLALCHEMY__` 접두사로 환경변수를 설정합니다.

```bash
# 필수
export SPAKKY_SQLALCHEMY__CONNECTION_STRING="postgresql+psycopg://user:pass@localhost/db"

# Engine option(선택)
export SPAKKY_SQLALCHEMY__ECHO="false"
export SPAKKY_SQLALCHEMY__ECHO_POOL="false"

# Connection pool option(선택)
export SPAKKY_SQLALCHEMY__POOL_SIZE="5"
export SPAKKY_SQLALCHEMY__POOL_MAX_OVERFLOW="10"
export SPAKKY_SQLALCHEMY__POOL_TIMEOUT="30.0"
export SPAKKY_SQLALCHEMY__POOL_RECYCLE="-1"
export SPAKKY_SQLALCHEMY__POOL_PRE_PING="false"

# Session option(선택)
export SPAKKY_SQLALCHEMY__SESSION_AUTOFLUSH="true"
export SPAKKY_SQLALCHEMY__SESSION_EXPIRE_ON_COMMIT="true"

# Transaction option(선택)
export SPAKKY_SQLALCHEMY__AUTOCOMMIT="true"

# 비동기 지원(선택)
export SPAKKY_SQLALCHEMY__SUPPORT_ASYNC_MODE="true"
```

## 사용법

### 도메인 매핑 테이블 정의

`@Table` decorator와 `AbstractMappableTable` 상속으로 domain model mapping이 있는 ORM table을 정의합니다.

```python
from uuid import UUID
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from spakky.plugins.sqlalchemy.orm.table import AbstractMappableTable, Table
from spakky.domain.models.aggregate_root import AbstractAggregateRoot

# Domain model
class User(AbstractAggregateRoot[UUID]):
    id: UUID
    name: str
    email: str

# domain mapping을 가진 table 정의
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

### Repository 구현

`AbstractGenericRepository` 또는 `AbstractAsyncGenericRepository`를 확장합니다:

```python
from uuid import UUID
from spakky.data.stereotype.repository import Repository
from spakky.plugins.sqlalchemy.persistency.repository import (
    AbstractGenericRepository,
    AbstractAsyncGenericRepository,
)

# 동기 repository
@Repository()
class UserRepository(AbstractGenericRepository[User, UUID]):
    pass  # CRUD method 상속

# 비동기 repository
@Repository()
class AsyncUserRepository(AbstractAsyncGenericRepository[User, UUID]):
    pass  # 비동기 CRUD method 상속
```

### 트랜잭션 사용

`spakky-data`의 `@Transactional` decorator를 사용합니다.

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

### 비동기 트랜잭션

같은 `@Transactional()` decorator가 동기와 비동기 메서드 모두에서 동작합니다.
프레임워크는 메서드가 coroutine인지에 따라 올바른 aspect를 자동 선택합니다.

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

### Session 직접 접근

복잡한 query는 **QueryUseCase**에서 SQLAlchemy session에 직접 접근합니다.
CQRS 원칙에 따라 query는 repository에 query 메서드를 추가하지 않고 직접 구현해야 합니다.

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

migration용 table metadata를 얻으려면 `SchemaRegistry`에 접근합니다:

```python
from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry

@Pod()
class MigrationService:
    def __init__(self, schema_registry: SchemaRegistry) -> None:
        self._schema_registry = schema_registry

    def get_metadata(self) -> MetaData:
        return self._schema_registry.metadata
```

## 주요 기능

- **Domain-Table mapping**: domain model과 ORM table 간 양방향 변환
- **Generic repository**: composite PK를 지원하는 사전 구성 CRUD operation
- **동기/비동기 지원**: 동기 및 비동기 operation 모두 지원
- **Scoped session**: thread/context-safe session 관리
- **낙관적 lock**: 동시 update를 위한 내장 `VersionConflictError`
- **Schema registry**: 중앙화된 table metadata 관리

## 구성 요소

| 컴포넌트 | 설명 |
|-----------|-------------|
| `@Table` | domain mapping이 있는 ORM table 등록 decorator |
| `AbstractTable` | ORM table 기반 클래스(domain mapping 없는 infrastructure table) |
| `AbstractMappableTable` | `from_domain`/`to_domain` domain mapping을 가진 generic table |
| `AbstractGenericRepository` | CRUD operation을 가진 동기 repository |
| `AbstractAsyncGenericRepository` | CRUD operation을 가진 비동기 repository |
| `SchemaRegistry` | table-domain mapping 중앙 registry |
| `SessionManager` | 동기 scoped session 관리 |
| `AsyncSessionManager` | 비동기 scoped session 관리 |
| `Transaction` | 동기 transaction 구현 |
| `AsyncTransaction` | 비동기 transaction 구현 |
| `ConnectionManager` | 동기 SQLAlchemy engine lifecycle |
| `AsyncConnectionManager` | 비동기 SQLAlchemy engine lifecycle |
| `SQLAlchemyConnectionConfig` | 환경변수 기반 설정 |

## Repository 메서드

동기/비동기 repository는 모두 다음을 제공합니다:

| 메서드 | 설명 |
|--------|-------------|
| `get(id)` | ID로 aggregate 조회, 없으면 `EntityNotFoundError` 발생 |
| `get_or_none(id)` | ID로 aggregate 조회, 없으면 `None` 반환 |
| `contains(id)` | aggregate 존재 여부 확인 |
| `range(ids)` | ID 목록으로 여러 aggregate 조회 |
| `save(aggregate)` | aggregate 저장(insert 또는 update) |
| `save_all(aggregates)` | 여러 aggregate 저장 |
| `delete(aggregate)` | aggregate 삭제 |
| `delete_all(aggregates)` | 여러 aggregate 삭제 |

## 라이선스

MIT License
