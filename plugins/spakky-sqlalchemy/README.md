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

### 전체 흐름

`spakky-sqlalchemy`는 `spakky-data`의 추상 계약을 SQLAlchemy로 구현합니다.

1. 도메인 Aggregate를 정의합니다.
2. `@Table(Domain)`과 `AbstractMappableTable[Domain]`으로 ORM table을 매핑합니다.
3. `AbstractGenericRepository` 또는 `AbstractAsyncGenericRepository`를 상속한
   `@Repository()`를 등록합니다.
4. Command UseCase에는 Repository를 주입하고 `@Transactional()`로 transaction 경계를 둡니다.
5. 복잡한 조회는 Repository에 `find_by_*` 메서드를 추가하지 않고 QueryUseCase에서
   `SessionManager` / `AsyncSessionManager`를 직접 사용합니다.

자세한 end-to-end 예제는 [데이터베이스 가이드](../../docs/guides/sqlalchemy.md)를 참고하세요.

### 도메인 매핑 테이블 정의

`@Table` decorator와 `AbstractMappableTable` 상속으로 domain model mapping이 있는 ORM table을 정의합니다.

```python
from typing import Self
from uuid import UUID

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from spakky.domain.models.aggregate_root import AbstractAggregateRoot
from spakky.plugins.sqlalchemy.orm.table import AbstractMappableTable, Table

# Domain model
class User(AbstractAggregateRoot[UUID]):
    name: str
    email: str

# domain mapping을 가진 table 정의
@Table(User)
class UserTable(AbstractMappableTable[User]):
    __tablename__ = "users"

    uid: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))

    @classmethod
    def from_domain(cls, domain: User) -> Self:
        return cls(uid=domain.uid, name=domain.name, email=domain.email)

    def to_domain(self) -> User:
        return User(uid=self.uid, name=self.name, email=self.email)
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
from sqlalchemy import select


@immutable
class FindUserByEmailQuery(AbstractQuery):
    email: str


@immutable
class UserDTO:
    uid: UUID
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
        return UserDTO(uid=table.uid, name=table.name, email=table.email)
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

## Outbox Contribution

`spakky-sqlalchemy` base plugin은 SQLAlchemy connection, session, transaction,
schema registry만 등록합니다. SQLAlchemy 기반 Outbox storage/table은 별도 feature
contribution으로 제공합니다.

Outbox integration이 필요하면 `spakky-outbox`와 함께 설치하거나 SQLAlchemy plugin의
`outbox` extra를 사용합니다.

```bash
pip install "spakky-sqlalchemy[outbox]"
```

```toml
[project.entry-points."spakky.contributions.spakky.outbox"]
spakky-sqlalchemy = "spakky.plugins.sqlalchemy.contributions.outbox:initialize"
```

이 contribution은 `spakky-outbox` feature와 `spakky-sqlalchemy` provider가 모두
active일 때 base plugin 이후 로드됩니다. `load_plugins(include=...)`를 사용한다면
include set에 두 plugin을 모두 넣어야 합니다. `save()`는 현재 transactional session을
사용하므로 비즈니스 데이터와 Outbox 메시지가 같은 DB transaction 안에서 commit 또는
rollback됩니다.

```python
from spakky.plugins.sqlalchemy.outbox.storage import AsyncSqlAlchemyOutboxStorage

storage = app.container.get(type_=AsyncSqlAlchemyOutboxStorage)
```

## Agent Persistence Contribution

`spakky-agent`의 durable state, signal, evidence repository는 production
in-memory fallback을 두지 않고 provider contribution으로만 공급됩니다.
SQLAlchemy 구현은 별도 `spakky-agent-sqlalchemy` 패키지를 만들지 않고 이
패키지의 `agent` extra와 contribution entry point로 제공합니다.

```bash
pip install "spakky-sqlalchemy[agent]"
```

```toml
[project.entry-points."spakky.contributions.spakky.agent"]
spakky-sqlalchemy = "spakky.plugins.sqlalchemy.contributions.agent:initialize"
```

`spakky-agent`와 `spakky-sqlalchemy` base plugin이 함께 active이면 contribution loader가
`AgentStateTable`, `AgentSignalTable`, `AgentEvidenceTable`과 세 repository 구현을 등록합니다.
`AgentExecutionSpec(recovery=RecoveryStrategy.ACTION_BOUNDARY)` 또는 `accepted_signals`를
사용하는 Agent는 bootstrap 시 `IAgentStateRepository`, `IAgentSignalRepository`,
`IAgentEvidenceRepository`를 모두 요구하므로, 이 contribution이 누락되면 core가
`AgentPersistenceConfigurationError`로 실패합니다. 이 패키지는 production in-memory
fallback을 제공하지 않습니다.

`spakky-agent`와 `spakky-sqlalchemy`가 모두 active이면 다음 Pod과 schema가
등록됩니다.

- `SqlAlchemyAgentStateRepository`
- `SqlAlchemyAgentSignalRepository`
- `SqlAlchemyAgentEvidenceRepository`
- `spakky_agent_state`, `spakky_agent_signal`, `spakky_agent_evidence`

각 repository는 현재 SQLAlchemy transactional session을 사용합니다. Signal은
`consumed_at`으로 pending queue를 구분하고, Evidence repository는 append/read
메서드만 노출해 agent-facing append-only 계약을 유지합니다.

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
| `SqlAlchemyAgentStateRepository` | `IAgentStateRepository`의 SQLAlchemy 구현 |
| `SqlAlchemyAgentSignalRepository` | `IAgentSignalRepository`의 SQLAlchemy 구현. `consumed_at`으로 pending signal queue를 구분 |
| `SqlAlchemyAgentEvidenceRepository` | `IAgentEvidenceRepository`의 SQLAlchemy 구현. append/read만 노출 |

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
