# 데이터베이스 (SQLAlchemy)

`spakky-data`는 Repository와 Transaction의 추상 계약을 제공합니다. 실제 SQLAlchemy
engine, session, table mapping, repository 구현체는 `spakky-sqlalchemy` 플러그인이
등록합니다.

일반적인 데이터 접근 흐름은 다음과 같습니다.

1. 도메인 Aggregate를 정의합니다.
2. `AbstractMappableTable[T]`와 `@Table(T)`로 SQLAlchemy table을 도메인에 매핑합니다.
3. `AbstractAsyncGenericRepository[T, ID]` 또는 `AbstractGenericRepository[T, ID]`를
   상속한 Repository Pod를 등록합니다.
4. Command UseCase에 Repository를 주입하고 `@Transactional()`을 붙입니다.
5. 복잡한 조회는 Repository에 메서드를 추가하지 않고 QueryUseCase에서 SQLAlchemy session을
   직접 사용합니다.

---

## 설치

```bash
pip install spakky-data spakky-sqlalchemy
```

Spakky extras를 사용한다면 다음처럼 설치할 수 있습니다.

```bash
pip install spakky[sqlalchemy]
```

---

## 설정

`spakky-sqlalchemy`는 `SPAKKY_SQLALCHEMY__` 접두사의 환경변수를 읽습니다.

```bash
export SPAKKY_SQLALCHEMY__CONNECTION_STRING="postgresql+psycopg://user:pass@localhost/mydb"
export SPAKKY_SQLALCHEMY__ECHO="false"
export SPAKKY_SQLALCHEMY__AUTOCOMMIT="true"
export SPAKKY_SQLALCHEMY__SUPPORT_ASYNC_MODE="true"
```

애플리케이션은 플러그인을 로드한 뒤 도메인, ORM table, Repository, UseCase가 들어 있는
패키지를 scan해야 합니다.

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

import apps

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()
    .scan(apps)
    .start()
)
```

`SUPPORT_ASYNC_MODE=false`로 설정하면 `AsyncConnectionManager`, `AsyncSessionManager`,
`AsyncTransaction`, `AsyncSqlAlchemyOutboxStorage`가 등록되지 않습니다. async driver를
쓰지 않는 서비스에서는 false로 둘 수 있고, async Repository를 쓰는 서비스에서는 true가
필요합니다.

---

## 도메인 Aggregate

Repository는 도메인 Aggregate의 영속화 전용 포트입니다. 아래 예제의 `User`는
`spakky-domain`의 `AbstractAggregateRoot`를 상속합니다.

```python
from typing import Self
from uuid import UUID

from spakky.core.common.mutability import mutable
from spakky.core.utils.uuid import uuid7
from spakky.domain.models.aggregate_root import AbstractAggregateRoot


@mutable
class User(AbstractAggregateRoot[UUID]):
    username: str
    email: str
    password_hash: str

    @classmethod
    def next_id(cls) -> UUID:
        return uuid7()

    @classmethod
    def create(cls, username: str, email: str, password_hash: str) -> Self:
        return cls(
            uid=cls.next_id(),
            username=username,
            email=email,
            password_hash=password_hash,
        )

    def validate(self) -> None:
        return
```

---

## ORM 테이블 매핑

도메인 Aggregate와 DB table 사이의 변환은 `AbstractMappableTable[T]`가 담당합니다.
`@Table(User)`는 table을 `SchemaRegistry`에 등록하므로 Repository가 도메인 타입만으로
table을 찾을 수 있습니다.

```python
from datetime import datetime
from typing import Self
from uuid import UUID

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from spakky.plugins.sqlalchemy.orm.table import AbstractMappableTable, Table


@Table(User)
class UserTable(AbstractMappableTable[User]):
    __tablename__ = "users"

    uid: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    version: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    @classmethod
    def from_domain(cls, domain: User) -> Self:
        return cls(
            uid=domain.uid,
            version=domain.version,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
            username=domain.username,
            email=domain.email,
            password_hash=domain.password_hash,
        )

    def to_domain(self) -> User:
        return User(
            uid=self.uid,
            version=self.version,
            created_at=self.created_at,
            updated_at=self.updated_at,
            username=self.username,
            email=self.email,
            password_hash=self.password_hash,
        )
```

도메인 매핑이 없는 인프라 table은 `AbstractTable`을 직접 상속합니다. 예를 들어 Outbox
table은 도메인 Aggregate Repository의 대상이 아니므로 mappable table로 만들지 않습니다.

---

## Repository 구현

`spakky-data`의 `IAsyncGenericRepository`는 계약이고, `spakky-sqlalchemy`의
`AbstractAsyncGenericRepository`는 그 계약을 SQLAlchemy session으로 구현한 기본 클래스입니다.

```python
from uuid import UUID

from spakky.data.stereotype.repository import Repository
from spakky.plugins.sqlalchemy.persistency.repository import (
    AbstractAsyncGenericRepository,
    AbstractGenericRepository,
)


@Repository()
class UserRepository(AbstractGenericRepository[User, UUID]):
    pass


@Repository()
class AsyncUserRepository(AbstractAsyncGenericRepository[User, UUID]):
    pass
```

기본 Repository는 다음 연산만 제공합니다.

| 메서드 | 용도 |
|--------|------|
| `get(id)` | ID로 Aggregate 조회, 없으면 `EntityNotFoundError` |
| `get_or_none(id)` | ID로 Aggregate 조회, 없으면 `None` |
| `contains(id)` | ID 존재 여부 확인 |
| `range(ids)` | ID 목록으로 여러 Aggregate 조회 |
| `save(aggregate)` | Aggregate 저장 |
| `save_all(aggregates)` | 여러 Aggregate 저장 |
| `delete(aggregate)` | Aggregate 삭제 |
| `delete_all(aggregates)` | 여러 Aggregate 삭제 |

`find_by_email`, `search_by_status` 같은 조회 메서드는 Repository에 추가하지 않습니다.
Repository는 Aggregate 저장소 역할만 하고, 조회 모델은 QueryUseCase에서 별도로 다룹니다.

---

## Command UseCase와 트랜잭션

`@Transactional()`은 메서드가 성공하면 commit하고 예외가 발생하면 rollback합니다. 비동기
메서드에는 `AsyncTransactionalAspect`, 동기 메서드에는 `TransactionalAspect`가 자동 적용됩니다.

```python
from spakky.core.stereotype.usecase import UseCase
from spakky.data.aspects.transactional import Transactional


@UseCase()
class CreateUserUseCase:
    def __init__(self, user_repo: AsyncUserRepository) -> None:
        self._user_repo = user_repo

    @Transactional()
    async def execute(self, username: str, email: str, password_hash: str) -> User:
        user = User.create(
            username=username,
            email=email,
            password_hash=password_hash,
        )
        return await self._user_repo.save(user)
```

괄호 없는 shorthand가 필요하면 `@transactional`을 사용할 수 있습니다.

```python
from spakky.data.aspects.transactional import transactional


@UseCase()
class TouchUserUseCase:
    def __init__(self, user_repo: AsyncUserRepository) -> None:
        self._user_repo = user_repo

    @transactional
    async def execute(self, user_id: UUID) -> User:
        user = await self._user_repo.get(user_id)
        return await self._user_repo.save(user)
```

---

## QueryUseCase에서 직접 조회

복잡한 query는 Repository에 추가하지 않고 SQLAlchemy session을 직접 사용합니다. 이렇게 하면
Command 모델은 Aggregate Repository에 머물고, 조회 모델은 DTO 중심으로 독립시킬 수 있습니다.

```python
from uuid import UUID

from sqlalchemy import select

from spakky.core.common.mutability import immutable
from spakky.core.stereotype.usecase import UseCase
from spakky.domain.application.query import AbstractQuery, IAsyncQueryUseCase
from spakky.plugins.sqlalchemy.persistency.session_manager import AsyncSessionManager


@immutable
class FindUserByEmailQuery(AbstractQuery):
    email: str


@immutable
class UserDTO:
    uid: UUID
    username: str
    email: str


@UseCase()
class FindUserByEmailUseCase(
    IAsyncQueryUseCase[FindUserByEmailQuery, UserDTO | None]
):
    def __init__(self, session_manager: AsyncSessionManager) -> None:
        self._session_manager = session_manager

    async def run(self, query: FindUserByEmailQuery) -> UserDTO | None:
        result = await self._session_manager.session.execute(
            select(UserTable).where(UserTable.email == query.email)
        )
        table = result.scalar_one_or_none()
        if table is None:
            return None
        return UserDTO(
            uid=table.uid,
            username=table.username,
            email=table.email,
        )
```

QueryUseCase가 session을 쓰려면 트랜잭션 경계 안에서 실행되어야 합니다. 조회 전용 작업도
일관된 session lifecycle이 필요하면 `@Transactional()`을 붙여 같은 방식으로 관리합니다.

---

## SchemaRegistry와 메타데이터

`SchemaRegistry`는 `@Table`로 등록된 table과 domain 타입의 매핑을 보관합니다. migration,
테스트 schema 생성, metadata inspection이 필요한 코드에서 주입받을 수 있습니다.

```python
from sqlalchemy import MetaData

from spakky.core.stereotype.pod import Pod
from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry


@Pod()
class MigrationMetadataProvider:
    def __init__(self, schema_registry: SchemaRegistry) -> None:
        self._schema_registry = schema_registry

    def get_metadata(self) -> MetaData:
        return self._schema_registry.metadata
```

---

## Outbox Contribution

SQLAlchemy 기반 Outbox storage/table은 `spakky-sqlalchemy` base plugin 본체가 아니라
`spakky.contributions.spakky.outbox` contribution에서 등록됩니다. 이 contribution은
`spakky-outbox` feature와 `spakky-sqlalchemy` provider가 모두 active일 때 base plugin
이후 로드됩니다. `load_plugins(include=...)`를 사용한다면 두 plugin을 모두 include set에
넣어야 합니다. 설치 시에는 `spakky-outbox`를 별도로 추가하거나
`spakky-sqlalchemy[outbox]` extra를 사용하세요. `save()`는 현재 transactional session을 사용하므로 비즈니스 데이터와
Outbox 메시지가 같은 DB transaction 안에서 commit 또는 rollback됩니다.

```python
from spakky.plugins.sqlalchemy.outbox.storage import AsyncSqlAlchemyOutboxStorage

storage = app.container.get(type_=AsyncSqlAlchemyOutboxStorage)
```

---

## 선택 기준

| 작업 | 권장 위치 |
|------|-----------|
| Aggregate 저장, 삭제, ID 조회 | Repository |
| 이메일, 상태, 기간, join 기반 검색 | QueryUseCase + SQLAlchemy session |
| 외부 REST/gRPC/legacy system 조회 | `spakky-data` External Proxy |
| 여러 Aggregate와 외부 시스템을 잇는 장기 흐름 | Saga UseCase |
| 이벤트와 DB 변경의 원자적 저장 | `spakky-outbox` + `spakky-sqlalchemy` |
