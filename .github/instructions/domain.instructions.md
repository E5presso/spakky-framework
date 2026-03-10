---
applyTo: "**/domain/**/*.py"
---

# 도메인 레이어 규칙

## 핵심 빌딩 블록

| 클래스 | Import Path | 용도 |
|--------|------------|------|
| `AbstractEntity[UID]` | `spakky.domain.models.entity` | 식별자를 가진 도메인 객체 |
| `AbstractAggregateRoot[UID]` | `spakky.domain.models.aggregate_root` | 일관성 경계의 루트 엔티티 |
| `AbstractValueObject` | `spakky.domain.models.value_object` | 속성으로만 비교되는 불변 객체 |
| `AbstractDomainEvent` | `spakky.domain.models.event` | 도메인 내부 상태 변화 이벤트 |
| `AbstractIntegrationEvent` | `spakky.domain.models.event` | 경계 컨텍스트 간 통신 이벤트 |

## Entity / AggregateRoot

- `next_id()` 클래스 메서드 필수 구현
- 이벤트: `add_event(event)` 로 등록 (루트에서만)

```python
from dataclasses import dataclass
from uuid import UUID
from spakky.core.utils.uuid import uuid7
from spakky.domain.models.aggregate_root import AbstractAggregateRoot

@dataclass
class Order(AbstractAggregateRoot[UUID]):
    customer_id: UUID

    @classmethod
    def next_id(cls) -> UUID:
        return uuid7()

    def place(self) -> None:
        self.add_event(OrderPlacedEvent(order_id=self.uid))
```

## ValueObject

- `validate()` 필수 구현 (`__post_init__` 자동 호출)
- 모든 필드는 hashable (mutable 컨테이너 금지 — `tuple` 사용)

```python
from dataclasses import dataclass
from spakky.domain.models.value_object import AbstractValueObject

@dataclass(frozen=True)
class Email(AbstractValueObject):
    address: str

    def validate(self) -> None:
        if "@" not in self.address:
            raise InvalidEmailError()
```

## Event

- `@immutable` (frozen dataclass) — 이벤트는 변경 불가
- **DomainEvent**: 과거분사형, 접미사 없음 (`OrderPlaced` ✅ / `OrderPlacedEvent` ❌)
- **IntegrationEvent**: `IntegrationEvent` 접미사 사용

```python
from dataclasses import dataclass
from uuid import UUID
from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent

@dataclass
class OrderPlaced(AbstractDomainEvent):
    order_id: UUID

@dataclass
class OrderPlacedIntegrationEvent(AbstractIntegrationEvent):
    order_id: UUID
```

## 도메인 에러

```python
from spakky.domain.error import AbstractSpakkyDomainError

class InvalidQuantityError(AbstractSpakkyDomainError):
    message = "Quantity must be greater than zero"
```

## 금지 사항

- 인프라 의존성 (`SQLAlchemy`, `httpx`, `aiokafka` 등) import 금지
- 도메인 객체에서 I/O 수행 금지

