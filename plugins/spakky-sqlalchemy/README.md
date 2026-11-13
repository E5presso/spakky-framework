# Spakky SQLAlchemy

> [Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 SQLAlchemy 통합 플러그인입니다.
> Connection/session/transaction Pod와 outbox/agent persistence contribution을 SQLAlchemy로 제공합니다.

## 설치

```bash
pip install spakky-sqlalchemy
```

Spakky extras로도 설치할 수 있습니다.

```bash
pip install spakky[sqlalchemy]
```

PostgreSQL 예제를 그대로 따라간다면 driver까지 포함하는 extra를 사용하세요.

```bash
pip install "spakky[database-postgres]"
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
export SPAKKY_DATA__SUPPORT_ASYNC_MODE="true"
```

비동기 지원 여부는 `spakky.data.config.DataConfig`의 공통 설정입니다.
SQLAlchemy는 이 설정에 맞춰 비동기 연결·세션·트랜잭션과 Outbox 구현을 등록합니다.
이전 `SPAKKY_SQLALCHEMY__SUPPORT_ASYNC_MODE`는 제거됐으므로 위 Data 변수로 변경하세요.

`postgresql+psycopg://` connection string은 `psycopg` driver가 필요합니다.
`spakky[database-postgres]`를 쓰거나 프로젝트 의존성에 `psycopg[binary]`를 직접 추가하세요.

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

### 스키마 업그레이드 — `partition_key` 컬럼 추가

`OutboxMessageTable`은 migration용 metadata만 제공하고 운영 스키마 적용은 사용자
migration이 소유합니다. 이미 `spakky_event_outbox`가 배포된 환경을 이 버전으로
올릴 때는 아래 DDL을 직접 실행해야 합니다.

```sql
ALTER TABLE spakky_event_outbox ADD COLUMN partition_key TEXT NULL;
```

미적용 시 `save()`의 INSERT가 비즈니스 트랜잭션과 함께 롤백되고, 릴레이의
`fetch_pending()` SELECT 실패는 재시도 `try` 블록 밖이라 릴레이 백그라운드
서비스가 종료됩니다. 증상과 배경은 Outbox 가이드(`docs/guides/outbox.md`)를
참고하십시오.

## Event Contribution (멱등 소비 저장소)

`spakky-event`의 멱등 소비(`@Idempotent()`)가 쓰는 처리 기록 저장소를 SQLAlchemy로 제공합니다.

```bash
pip install "spakky-sqlalchemy[event]"
```

```toml
[project.entry-points."spakky.contributions.spakky.event"]
spakky-sqlalchemy = "spakky.plugins.sqlalchemy.contributions.event:initialize"
```

이 contribution은 `spakky-event` feature와 `spakky-sqlalchemy` provider가 모두 active일 때 로드되어 다음을 등록합니다. 비동기 저장소는 `SPAKKY_DATA__SUPPORT_ASYNC_MODE`가 켜져 있을 때만 등록됩니다.

| 구성 요소 | 역할 |
| --- | --- |
| `ProcessedEventTable` | `spakky_event_inbox` 테이블. 기본 키는 `(subscriber, handler, event_id)`이고 `processed_at`에 인덱스가 있습니다 |
| `SqlAlchemyProcessedEventStore` | `IProcessedEventStore` 구현 |
| `AsyncSqlAlchemyProcessedEventStore` | `IAsyncProcessedEventStore` 구현 |

```python
from spakky.data.aspects.transactional import Transactional
from spakky.event.idempotency import Idempotent
from spakky.event.stereotype.event_handler import EventHandler, on_event


@EventHandler(subscriber="billing")
class BillingHandler:
    @on_event(OrderPlaced)
    @Transactional()
    @Idempotent()
    async def charge(self, event: OrderPlaced) -> None: ...
```

- 저장소는 `@Transactional()`이 연 현재 세션으로 기록하므로, 처리 기록과 처리기의 업무 변경이 같은 트랜잭션에서 commit 또는 rollback됩니다. 트랜잭션 없이 호출하면 `SessionNotInitializedError`가 납니다.
- 같은 이벤트가 동시에 두 번 전달되면 나중 쪽의 기록이 기본 키 충돌로 `DuplicateProcessedEventError`가 되고 그 트랜잭션은 롤백됩니다. 이 오류는 유예(`EventDeferredError`)라서 시도 횟수를 세지 않고 다시 전달되며, 다시 전달된 쪽은 커밋된 기록을 보고 건너뜁니다.
- 테이블은 `SchemaRegistry` 메타데이터에 포함됩니다. 마이그레이션 도구를 쓴다면 `spakky_event_inbox` 테이블 생성을 마이그레이션에 추가하세요.
- 오래된 기록은 트랜잭션 안에서 `store.purge(older_than)`으로 지웁니다. 보존 기간은 브로커가 같은 메시지를 다시 전달할 수 있는 기간보다 길게 잡습니다.

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
`AgentStateTable`, `AgentSignalTable`, `AgentEvidenceTable`, `AgentConversationTurnTable`과
세 repository 구현, `ITaskStore` 구현(`SqlAlchemyAgentTaskStore`)을 등록합니다.
`AgentExecutionSpec(recovery=RecoveryStrategy.ACTION_BOUNDARY)` 또는 `accepted_signals`를
사용하는 Agent는 bootstrap 시 `IAgentStateRepository`, `IAgentSignalRepository`,
`IAgentEvidenceRepository`를 모두 요구하므로, 이 contribution이 누락되면 core가
`AgentPersistenceConfigurationError`로 실패합니다. 이 패키지는 운영용 in-memory fallback을
제공하지 않습니다.

`spakky-agent`와 `spakky-sqlalchemy`가 모두 active이면 다음 Pod과 schema가
등록됩니다.

- `SqlAlchemyAgentStateRepository`
- `SqlAlchemyAgentSignalRepository`
- `SqlAlchemyAgentEvidenceRepository`
- `SqlAlchemyAgentTaskStore`
- `spakky_agent_state`, `spakky_agent_signal`, `spakky_agent_evidence`,
  `spakky_agent_evidence_origin`, `spakky_agent_conversation_turn`

State metadata(runner checkpoint 포함), signal payload, evidence payload는 형식이 자유로운
값이므로 JSON 열에 저장합니다.

Evidence의 `model_step`은 열로 저장해 같은 step의 context 근거를 색인으로 확인합니다
(`has_step_evidence`). `count_by_state`는 개수 질의를 씁니다. Context manifest의
`origin_refs`는 `spakky_agent_evidence_origin`에 행으로 저장해 `list_by_origin_ref`가 어떤
실행이 그 출처를 읽었는지 찾습니다.

각 repository는 현재 SQLAlchemy transactional session을 사용합니다. Signal은
`consumed_at`으로 pending queue를 구분하는 원장이며, `IAgentSignalPublisher`가
주입되면(`spakky-agent`가 기본 `InProcessAgentSignalMailbox`를 등록) 가장 바깥
트랜잭션이 커밋될 때만 실행 중 Agent의 메일박스로 게시합니다. 해제된 savepoint의
행은 바깥 커밋을 기다리고, savepoint 롤백은 그 안의 행만, 바깥 롤백이나
`close()`는 남은 행을 모두 버립니다. `AgentSignal.priority`는 실시간 전달 힌트라 테이블에 저장하지 않습니다.
 Evidence repository는 append/read
메서드만 노출해 agent-facing append-only 계약을 유지합니다.

`SqlAlchemyAgentTaskStore`는 `ITaskStore`(server-side 멀티턴 transcript)의 구현입니다.
`append_turns(conversation_id, turns)`는 그 대화의 마지막 `position` 뒤에 turn을 순서대로
추가하고, `load_history(conversation_id)`는 `position` 순서로 `ConversationTurn`을 돌려줍니다.
`spakky_agent_conversation_turn`은 `(conversation_id, position)` unique 제약을 가지므로, 두
writer가 같은 대화에 동시에 append하면 한쪽만 저장되고 다른 쪽은
`AgentConversationAppendConflictError`로 실패합니다. turn이 조용히 뒤섞이거나 순서가 바뀌지
않습니다. 실패한 쪽은 트랜잭션을 rollback하고 이력을 다시 읽어 재시도해야 합니다. 다른
repository와 마찬가지로 현재 transactional session 안에서 호출합니다. Agent는 생성자에서
`ITaskStore`를 주입받으면 됩니다.

```python
from spakky.agent import Agent, AgentExecutionSpec, IAgentModel, ITaskStore


@Agent(spec=AgentExecutionSpec(name="assistant"))
class Assistant:
    def __init__(self, model: IAgentModel, task_store: ITaskStore) -> None:
        self.model = model
        self.task_store = task_store
```

## 주요 기능

- **Domain-Table mapping**: domain model과 ORM table 간 양방향 변환
- **Generic repository**: composite PK를 지원하는 사전 구성 CRUD operation
- **동기/비동기 지원**: 동기 및 비동기 operation 모두 지원
- **Scoped session**: thread/context-safe session 관리
- **낙관적 lock**: Aggregate table의 `version` column을 `version_id_col`로 자동 매핑하고, 동시 update·delete 충돌을 `VersionConflictError`로 보고
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
| `SqlAlchemyAgentSignalRepository` | `IAgentSignalRepository`의 SQLAlchemy 구현. `consumed_at`으로 pending signal queue를 구분하고, 주입된 `IAgentSignalPublisher`로 커밋 뒤에만 게시 |
| `SqlAlchemyAgentEvidenceRepository` | `IAgentEvidenceRepository`의 SQLAlchemy 구현. append/read만 노출 |
| `SqlAlchemyAgentTaskStore` | `ITaskStore`의 SQLAlchemy 구현. 대화별 transcript를 `position` 순서로 append/조회 |

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

## 낙관적 lock

`AbstractMappableTable[T]`의 `T`가 `AbstractAggregateRoot`이고 table에 `version` column이
있으면, 그 column이 SQLAlchemy mapper의 `version_id_col`로 자동 설정됩니다
(`version_id_generator=False`). 별도 설정은 필요 없습니다.

Aggregate는 비즈니스 필드가 바뀔 때마다 `version`을 새로 만들고, 불러올 때의 version은
`persisted_version`으로 기억합니다. Repository의 `save`/`save_all`/`delete`/`delete_all`은
이 값을 사용합니다.

1. `persisted_version`을 담은 table 객체로 `merge()`합니다. 저장된 행의 version과 다르면 여기서 충돌입니다.
2. 병합된 객체에 Aggregate의 새 `version`을 기록하고 `flush()`합니다. `UPDATE ... WHERE version = <불러온 version>`이 0행이면 충돌입니다.
3. 충돌은 `VersionConflictError`로 올라옵니다. 성공하면 `aggregate.mark_persisted()`가 호출되어 같은 인스턴스를 다시 변경·저장할 수 있습니다.

```python
from spakky.data.persistency.repository import VersionConflictError

try:
    await user_repo.save(user)
except VersionConflictError:
    ...  # 다시 조회해 재시도하거나 호출자에게 충돌을 알립니다
```

알아 둘 점:

- `to_domain()`은 저장된 `version`을 그대로 생성자에 넘겨야 합니다. 넘기지 않으면 매번 새 version이 만들어져 모든 저장이 충돌합니다.
- 조회하지 않고 이미 존재하는 `uid`로 새로 만든 Aggregate를 `save`하면 덮어쓰지 않고 `VersionConflictError`가 발생합니다.
- `save_all`/`delete_all`의 일괄 `flush()`에서 난 충돌은 어느 행인지 SQLAlchemy가 알려 주지 않으므로, 오류 인자에 대상 `uid` 전체가 담깁니다.
- `mark_persisted()`는 `flush()` 직후 호출됩니다. 이후 트랜잭션이 rollback되면 그 인스턴스는 버리고 다시 조회하세요.
- 자동 잠금은 `version` 컬럼의 Python 타입이 `UUID`일 때만 적용됩니다. 문자열이나 정수 등 다른 타입의 `version` 컬럼은 프레임워크가 건드리지 않으며 잠금도 걸리지 않습니다. `version_id_col`과 SQLAlchemy의 `version_id_generator`를 직접 선언한 테이블은 SQLAlchemy의 동작을 그대로 따르고, 충돌은 똑같이 `VersionConflictError`로 보고됩니다.
- `save_all()`과 `delete_all()`에 같은 인스턴스를 여러 번 넣으면 한 번만 처리합니다.
- 조회한 뒤 변경한 집합체를 `dataclasses.replace()`로 복사하면 복사본은 읽어 온 버전을 잃습니다. 원래 인스턴스를 저장하거나 다시 조회하세요.
- 기존 table에 `version` column이 이미 있다면 schema migration은 필요 없습니다. mapper 설정만 달라지고 DDL은 같습니다. 달라지는 것은 동작입니다. 지금까지 조용히 덮어쓰던 동시 저장이 `VersionConflictError`가 됩니다.
- column 이름이 `version`이 아니거나 Aggregate가 아닌 entity의 table(relationship으로 딸린 자식 table 포함)은 자동 대상이 아닙니다. 다른 column을 쓰려면 `__mapper_args__`에 `version_id_col`과 `version_id_generator=False`를 직접 지정합니다.
- table에 `__mapper_args__`를 직접 정의하면 SQLAlchemy 규칙대로 기본값을 대체합니다. `__mapper_args__ = {}`는 검사를 끕니다. 다른 mapper 인자를 쓰면서 검사를 유지하려면 `"version_id_col": version, "version_id_generator": False`를 함께 넣습니다.

## 개발 검증

패키지 단위 검증은 해당 패키지 디렉토리에서 실행합니다.

```bash
uv run ruff format .
uv run ruff check .
uv run pyrefly check
uv run pytest
```

`pytest`는 각 패키지 `pyproject.toml`의 coverage 설정을 사용합니다.

## 라이선스

MIT License

### 컨텍스트별 세션 수명

SessionManager와 AsyncSessionManager는 현재 ApplicationContext ID의 scoped session을 사용합니다. 다른 컨텍스트의 open/close가 원래 컨텍스트의 세션을 덮어쓰거나 종료하지 않습니다. 각 작업은 트랜잭션 경계에서 세션을 열고 닫으며, 열린 세션이 없을 때 session 접근은 SessionNotInitializedError를 발생시킵니다.


```bash
export SPAKKY_SQLALCHEMY__ASYNC_POOL_MODE="queue" # queue(default) 또는 null
```

## 여러 event loop에서 비동기 엔진 사용

HTTP와 ApplicationContext background service처럼 같은 `AsyncConnectionManager`를
서로 다른 event loop가 사용하면 `SPAKKY_SQLALCHEMY__ASYNC_POOL_MODE=null`을
설정합니다. SQLAlchemy `NullPool`은 checkout마다 연결을 만들고 반환 시 닫으므로
loop에 귀속된 연결과 asyncio queue를 공유하지 않습니다. 기본 `queue` 모드는
단일 loop용 기존 bounded pool 동작을 유지합니다. `null` 모드에서는
`POOL_SIZE`, `POOL_MAX_OVERFLOW`, `POOL_TIMEOUT`이 비동기 엔진에 적용되지 않습니다.
동시 연결 상한은 서버 또는 외부 pooler에서 제한하고, 연결 생성 비용을 고려해야 합니다.
동기 `ConnectionManager`의 pool 설정은 변경되지 않습니다.

`null` 모드의 `AsyncConnectionManager`는 framework service 시작 때 한 번 연결해
SQLAlchemy dialect의 최초 연결 초기화를 마칩니다. 이 초기화도 asyncio lock을
사용하므로 여러 loop에서 첫 연결을 동시에 시작하기 전에 끝나야 합니다. 직접 manager를
구성하는 코드도 `await manager.start_async()`를 먼저 호출합니다. 종료 hook은 NullPool을
정리합니다. 기본 `queue` 모드는 기존처럼 실제 사용 loop에서 `dispose()`를 호출합니다.

### 별도 동기 driver URL

`SPAKKY_SQLALCHEMY__SYNC_CONNECTION_STRING`은 `ConnectionManager`에만 적용하는
선택 설정입니다. 생략하면 기존 `CONNECTION_STRING`을 그대로 사용합니다. PostgreSQL
`postgresql+psycopg`처럼 하나의 driver가 양쪽 실행 모드를 지원하면 추가 설정이 필요
없습니다. SQLite에서는 base URL을 `sqlite+aiosqlite:///...`, sync URL을 같은 파일의
`sqlite+pysqlite:///...`로 지정해 async 업무와 sync runner/relay를 함께 사용할 수 있습니다.
