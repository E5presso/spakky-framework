# Spakky DDD

[Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 Domain-Driven Design 빌딩 블록입니다.

## 설치

```bash
pip install spakky-domain
```

## 주요 기능

- **Entity**: 고유 identity와 생명주기를 가진 객체
- **Value Object**: 속성 값으로 비교되는 불변 객체
- **Aggregate Root**: 이벤트 관리를 포함하는 일관성 경계
- **Domain Event**: 이벤트 기반 아키텍처를 위한 불변 이벤트
- **CQRS**: Command와 Query 유스케이스 추상화

## 빠른 시작

### 엔티티

엔티티는 시간이 지나도 유지되는 고유 identity를 가진 객체입니다.

```python
from uuid import UUID, uuid4

from spakky.core.common.mutability import mutable
from spakky.domain.models.entity import AbstractEntity


@mutable
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

### 값 객체

값 객체는 불변이며 속성 값으로 비교됩니다.

```python
from spakky.core.common.mutability import immutable
from spakky.domain.models.value_object import AbstractValueObject


@immutable
class Money(AbstractValueObject):
    amount: int
    currency: str

    def validate(self) -> None:
        if self.amount < 0:
            raise ValueError("Amount cannot be negative")
```

### 애그리거트 루트

애그리거트 루트는 도메인 이벤트를 관리하는 엔티티입니다.

```python
from uuid import UUID, uuid4

from spakky.core.common.mutability import mutable, immutable
from spakky.domain.models.aggregate_root import AbstractAggregateRoot
from spakky.domain.models.event import AbstractDomainEvent


@immutable
class OrderCreatedEvent(AbstractDomainEvent):
    order_id: UUID
    customer_id: UUID


@mutable
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

### 도메인 이벤트

도메인 이벤트는 도메인 내부의 상태 변화를 표현합니다.

```python
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent


# Internal domain event
@immutable
class UserRegistered(AbstractDomainEvent):
    user_id: str
    email: str


# Cross-boundary integration event
@immutable
class UserRegisteredIntegration(AbstractIntegrationEvent):
    user_id: str
    email: str
```

### CQRS 유스케이스

읽기와 쓰기 작업을 분리합니다.

**핵심 원칙:**
- **Command**: 도메인 Aggregate 영속화에 Repository 사용
- **Query**: ORM/SQL로 직접 구현(Repository에 query 메서드 추가 금지)
- Query 관심사를 도메인 레이어 밖에 두어 도메인 오염을 방지합니다.

```python
from uuid import UUID

from spakky.core.common.mutability import immutable
from spakky.domain.application.command import AbstractCommand, IAsyncCommandUseCase
from spakky.domain.application.query import AbstractQuery, IAsyncQueryUseCase


# Command
@immutable
class CreateUserCommand(AbstractCommand):
    name: str
    email: str


class CreateUserUseCase(IAsyncCommandUseCase[CreateUserCommand, UUID]):
    async def run(self, command: CreateUserCommand) -> UUID:
        # Business logic here
        ...


# Query
@immutable
class GetUserQuery(AbstractQuery):
    user_id: UUID


class GetUserUseCase(IAsyncQueryUseCase[GetUserQuery, User | None]):
    async def run(self, query: GetUserQuery) -> User | None:
        # Business logic here
        ...
```

## API 레퍼런스

### 모델

| 클래스                      | 설명                                    |
| -------------------------- | ---------------------------------------------- |
| `AbstractEntity[T]`        | identity type `T`를 가진 엔티티의 기반 클래스 |
| `AbstractAggregateRoot[T]` | 도메인 이벤트를 관리하는 Entity              |
| `AbstractValueObject`      | 불변 value object                         |
| `AbstractEvent`            | 모든 이벤트의 기반 클래스                      |
| `AbstractDomainEvent`      | 도메인 이벤트(bounded context 내부)         |
| `AbstractIntegrationEvent` | 통합 이벤트(경계 간 통신)            |

### 애플리케이션

| 클래스                  | 설명                      |
| ---------------------- | -------------------------------- |
| `AbstractCommand`      | command DTO의 기반 클래스      |
| `AbstractQuery`        | query DTO의 기반 클래스        |
| `ICommandUseCase`      | 동기 command use case interface  |
| `IAsyncCommandUseCase` | 비동기 command use case interface |
| `IQueryUseCase`        | 동기 query use case interface    |
| `IAsyncQueryUseCase`   | 비동기 query use case interface   |

## 관련 패키지

| 패키지 | 설명 |
|---------|-------------|
| `spakky-data` | Repository와 transaction 추상화 |
| `spakky-event` | Event publisher/consumer interface와 `@EventHandler` stereotype |

## 라이선스

MIT License
