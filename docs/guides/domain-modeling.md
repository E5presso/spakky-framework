# 도메인 모델링

Spakky Domain은 DDD(Domain-Driven Design)의 빌딩 블록을 제공합니다.

---

## Value Object

**값으로 동등성을 판단**하는 불변 객체입니다. ID가 없고, 모든 속성이 같으면 같은 객체입니다.

```python
from spakky.core.common.mutability import immutable
from spakky.domain.models.value_object import AbstractValueObject

@immutable
class Money(AbstractValueObject):
    amount: float
    currency: str

    def validate(self) -> None:
        if self.amount < 0:
            raise ValueError("금액은 0 이상이어야 합니다")

# 값이 같으면 동일
price_a = Money(amount=1000, currency="KRW")
price_b = Money(amount=1000, currency="KRW")
assert price_a == price_b
assert hash(price_a) == hash(price_b)

# 복제
price_c = price_a.clone()
assert price_a == price_c
```

---

## Entity

**ID로 동등성을 판단**하는 가변 객체입니다. 속성이 달라도 ID가 같으면 같은 엔티티입니다.

```python
from typing import Self
from uuid import UUID, uuid4
from spakky.core.common.mutability import mutable
from spakky.domain.models.entity import AbstractEntity

@mutable
class User(AbstractEntity[UUID]):
    name: str
    email: str

    def validate(self) -> None:
        if not self.name:
            raise ValueError("이름은 필수입니다")

    @classmethod
    def next_id(cls) -> UUID:
        return uuid4()

    @classmethod
    def create(cls: type[Self], name: str, email: str) -> Self:
        return cls(uid=cls.next_id(), name=name, email=email)

# ID가 같으면 동일
user_id = UUID("12345678-1234-5678-1234-567812345678")
user_a = User(uid=user_id, name="John", email="john@example.com")
user_b = User(uid=user_id, name="Sarah", email="sarah@example.com")
assert user_a == user_b  # ID 기반 동등성

# 새 ID = 다른 엔티티
user_c = User.create(name="Peter", email="peter@example.com")
assert user_a != user_c
```

---

## Aggregate Root

Entity를 확장하여 **도메인 이벤트 발행** 기능을 갖춘 루트 엔티티입니다.

```python
from uuid import UUID, uuid4

from spakky.core.common.mutability import mutable, immutable
from spakky.domain.models.aggregate_root import AbstractAggregateRoot
from spakky.domain.models.event import AbstractDomainEvent

@mutable
class Order(AbstractAggregateRoot[UUID]):
    customer_name: str
    total_amount: float
    items: list[str]

    def validate(self) -> None:
        if self.total_amount <= 0:
            raise ValueError("주문 금액은 0보다 커야 합니다")

    # 내부 도메인 이벤트 정의
    @immutable
    class Created(AbstractDomainEvent):
        order_id: UUID
        total_amount: float

    @immutable
    class ItemAdded(AbstractDomainEvent):
        order_id: UUID
        item_name: str

    @classmethod
    def next_id(cls) -> UUID:
        return uuid4()

    @classmethod
    def create(cls, customer_name: str, total_amount: float) -> "Order":
        order = cls(
            uid=cls.next_id(),
            customer_name=customer_name,
            total_amount=total_amount,
            items=[],
        )
        # 이벤트 발행
        order.add_event(Order.Created(
            order_id=order.uid,
            total_amount=total_amount,
        ))
        return order

    def add_item(self, item_name: str) -> None:
        self.items.append(item_name)
        self.add_event(Order.ItemAdded(
            order_id=self.uid,
            item_name=item_name,
        ))

# 사용
order = Order.create(customer_name="김철수", total_amount=50000)
order.add_item("노트북")
order.add_item("마우스")

assert len(order.events) == 3  # Created + ItemAdded x2
order.clear_events()  # 처리 후 초기화
```

---

## Domain Event vs Integration Event

| 구분        | Domain Event                | Integration Event             |
| ----------- | --------------------------- | ----------------------------- |
| 범위        | 같은 바운디드 컨텍스트 내부 | 바운디드 컨텍스트 간 통신     |
| 전달        | 인메모리 EventMediator      | EventBus (RabbitMQ, Kafka 등) |
| 기반 클래스 | `AbstractDomainEvent`       | `AbstractIntegrationEvent`    |

```python
from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent

# 내부용 — 같은 서비스 내 핸들러가 처리
@immutable
class OrderCreated(AbstractDomainEvent):
    order_id: UUID

# 외부용 — 메시지 브로커를 통해 다른 서비스에 전달
@immutable
class OrderConfirmed(AbstractIntegrationEvent):
    order_id: str
    total_amount: int
```

---

## CQRS 패턴

Command(명령)와 Query(조회)를 분리합니다.

```python
from spakky.core.stereotype.usecase import UseCase
from spakky.domain.application.command import AbstractCommand, ICommandUseCase
from spakky.domain.application.query import AbstractQuery, IQueryUseCase

# Command — 상태 변경
@immutable
class CreateOrderCommand(AbstractCommand):
    customer_name: str
    total_amount: float

@UseCase()
class CreateOrderUseCase(ICommandUseCase[CreateOrderCommand, Order]):
    def run(self, command: CreateOrderCommand) -> Order:
        return Order.create(
            customer_name=command.customer_name,
            total_amount=command.total_amount,
        )

# Query — 상태 조회
@immutable
class GetOrderQuery(AbstractQuery):
    order_id: UUID

@UseCase()
class GetOrderUseCase(IQueryUseCase[GetOrderQuery, Order]):
    def run(self, query: GetOrderQuery) -> Order:
        return self._repo.find_by_id(query.order_id)
```
