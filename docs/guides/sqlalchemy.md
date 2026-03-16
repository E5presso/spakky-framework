# 데이터베이스 (SQLAlchemy)

`spakky-sqlalchemy`는 SQLAlchemy 기반 트랜잭션, 리포지토리, ORM을 통합합니다.

---

## 설정

환경변수로 데이터베이스 연결을 구성합니다.

```bash
export SPAKKY_SQLALCHEMY__CONNECTION_STRING="postgresql+psycopg://user:pass@localhost/mydb"
export SPAKKY_SQLALCHEMY__ECHO="false"
export SPAKKY_SQLALCHEMY__AUTOCOMMIT="true"
```

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

---

## @Transactional

`@Transactional()`을 메서드에 붙이면 AOP 어스펙트가 트랜잭션을 자동으로 관리합니다.
성공 시 커밋, 예외 시 롤백. 동기/비동기 메서드 모두 동일하게 동작합니다.

괄호 없이 사용할 수 있는 shorthand `@transactional`도 제공됩니다.

### 비동기

```python
from spakky.core.stereotype.usecase import UseCase
from spakky.data.aspects.transactional import Transactional

@UseCase()
class CreateUserUseCase:
    _user_repo: UserRepository

    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo

    @Transactional()
    async def execute(self, name: str, email: str) -> User:
        user = User.create(name=name, email=email)
        return await self._user_repo.save(user)
        # 성공 → 자동 커밋
        # 예외 → 자동 롤백
```

### 동기

```python
@UseCase()
class SyncCreateUserUseCase:
    _user_repo: UserRepository

    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo

    @Transactional()
    def execute(self, name: str, email: str) -> User:
        user = User.create(name=name, email=email)
        return self._user_repo.save(user)
```

### Shorthand

```python
from spakky.data.aspects.transactional import transactional

@UseCase()
class QuickUseCase:
    @transactional
    async def execute(self) -> str:
        return "done"
```

`@transactional`은 `@Transactional()`과 동일하게 동작하는 함수형 shorthand입니다.

프레임워크가 메서드의 코루틴 여부를 자동 감지하여 `AsyncTransactionalAspect` 또는 `TransactionalAspect`를 적용합니다.

---

## ORM 테이블 매핑

### 테이블 정의

`AbstractMappableTable[T]`를 상속하고 `@Table(DomainClass)` 데코레이터를 붙여 도메인 모델과 테이블을 매핑합니다.
`from_domain()`, `to_domain()` 메서드를 반드시 구현해야 합니다.

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

    @classmethod
    def from_domain(cls, domain: User) -> Self:
        return cls(
            uid=domain.uid,
            version=domain.version,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
            username=domain.username,
            email=domain.email,
        )

    def to_domain(self) -> User:
        return User(
            uid=self.uid,
            version=self.version,
            created_at=self.created_at,
            updated_at=self.updated_at,
            username=self.username,
            email=self.email,
        )
```

`@Table(User)` 데코레이터가 `SchemaRegistry`의 태그 레지스트리에 자동 등록합니다.
도메인 매핑이 불필요한 인프라 테이블(아웃박스, 감사 로그 등)은 `AbstractTable`을 직접 상속합니다.

### SchemaRegistry

리포지토리 내부에서 도메인 ↔ 테이블 변환에 사용됩니다.

```python
# 도메인 → 테이블
table = schema_registry.from_domain(user)

# 테이블 → 도메인
domain = table.to_domain()

# 도메인 타입으로 테이블 클래스 조회
table_class = schema_registry.get_type(User)
```

---

## Outbox Storage

`spakky-sqlalchemy`는 Outbox 패턴의 SQLAlchemy 구현체도 제공합니다.

```python
from spakky.plugins.sqlalchemy.outbox.storage import SqlAlchemyOutboxStorage

# 자동으로 컨테이너에 등록됨
storage = app.container.get(type_=SqlAlchemyOutboxStorage)
```
