---
applyTo: "**/domain/**/*.py"
---

# 도메인 레이어 규칙

이 규칙은 `domain/` 경로 하위 모든 Python 파일에 자동 적용됩니다.

## 핵심 빌딩 블록

| 클래스 | Import Path | 용도 |
|--------|------------|------|
| `AbstractEntity` | `spakky.domain.models.entity` | 식별자를 가진 도메인 객체 |
| `AbstractAggregateRoot` | `spakky.domain.models.aggregate_root` | 일관성 경계의 루트 엔티티 |
| `AbstractValueObject` | `spakky.domain.models.value_object` | 속성으로만 비교되는 불변 객체 |
| `AbstractDomainEvent` | `spakky.domain.models.event` | 도메인 내부 상태 변화 이벤트 |
| `AbstractIntegrationEvent` | `spakky.domain.models.event` | 경계 컨텍스트 간 통신 이벤트 |

## Entity 패턴

- `AbstractEntity[UID_TYPE]`를 상속하고, `@mutable` 데코레이터가 이미 부모에 적용됨
- `next_id()` 클래스 메서드를 반드시 구현해야 함
- UID 타입 예: `UUID`, `int`, `str`

```python
from dataclasses import dataclass
from uuid import UUID
from spakky.core.utils.uuid import uuid7
from spakky.domain.models.entity import AbstractEntity

@dataclass
class Order(AbstractEntity[UUID]):
    customer_id: UUID
    total: int

    @classmethod
    def next_id(cls) -> UUID:
        return uuid7()
```

## AggregateRoot 패턴

- `AbstractAggregateRoot[UID_TYPE]`를 상속
- 도메인 이벤트는 `add_event(event)`로 등록, 외부 발행은 레포지토리/서비스에서 처리
- 집합체 내부 엔티티는 루트를 통해서만 접근

```python
from dataclasses import dataclass
from uuid import UUID
from spakky.domain.models.aggregate_root import AbstractAggregateRoot
from spakky.domain.models.event import AbstractDomainEvent

@dataclass
class OrderPlacedEvent(AbstractDomainEvent):
    order_id: UUID

@dataclass
class Order(AbstractAggregateRoot[UUID]):
    customer_id: UUID

    @classmethod
    def next_id(cls) -> UUID:
        return uuid7()

    def place(self) -> None:
        self.add_event(OrderPlacedEvent(order_id=self.uid))
```

## ValueObject 패턴

- `AbstractValueObject`를 상속, `@immutable` 데코레이터가 이미 부모에 적용됨
- `validate()` 메서드를 반드시 구현해야 함 (`__post_init__`에서 자동 호출)
- 모든 필드는 **hashable** 타입이어야 함

```python
from dataclasses import dataclass
from spakky.domain.models.value_object import AbstractValueObject
from spakky.domain.error import AbstractSpakkyDomainError

class InvalidEmailError(AbstractSpakkyDomainError):
    message = "Invalid email format"

@dataclass(frozen=True)
class Email(AbstractValueObject):
    address: str

    def validate(self) -> None:
        if "@" not in self.address:
            raise InvalidEmailError()
```

## DomainEvent / IntegrationEvent 패턴

- `@immutable` (frozen dataclass) — 이벤트는 변경 불가
- 이벤트명은 과거형 동사: `OrderPlacedEvent`, `UserCreatedEvent`
- 필드에 집합체 ID와 필요한 컨텍스트만 포함

```python
from dataclasses import dataclass
from uuid import UUID
from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent

@dataclass
class OrderPlacedEvent(AbstractDomainEvent):
    order_id: UUID
    customer_id: UUID

@dataclass
class OrderPlacedIntegrationEvent(AbstractIntegrationEvent):
    order_id: UUID
```

## 유효성 검사 에러

도메인 유효성 에러는 반드시 `AbstractSpakkyDomainError`를 상속합니다:

```python
from spakky.domain.error import AbstractSpakkyDomainError

class InvalidQuantityError(AbstractSpakkyDomainError):
    message = "Quantity must be greater than zero"
```

## 금지 사항

- 도메인 레이어에서 인프라 의존성 (`SQLAlchemy`, `httpx`, `aiokafka` 등) 직접 import 금지
- 도메인 객체에서 I/O 작업 수행 금지
- `AbstractValueObject` 필드에 mutable 컨테이너(`list`, `dict`, `set`) 금지 — `tuple` 사용
