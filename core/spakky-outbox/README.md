# spakky-outbox

[Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 트랜잭셔널 Outbox 패턴 패키지입니다.

## 설치

```bash
pip install spakky-outbox "spakky-sqlalchemy[outbox]"
```

> **참고**: `spakky-outbox`는 core abstraction을 제공하고, `spakky-sqlalchemy`는
> `spakky.contributions.spakky.outbox` contribution으로 Outbox storage 구현체를
> 제공합니다. `spakky-sqlalchemy` 단독 설치는 `spakky-outbox`를 끌어오지
> 않습니다.

## 주요 기능

- **트랜잭셔널 Outbox**: 이벤트를 비즈니스 데이터와 원자적으로 저장
- **자동 relay**: background relay가 이벤트를 외부 transport(Kafka, RabbitMQ)로 발행
- **재시도 지원**: 실패 메시지를 설정 가능한 한도 내에서 재시도
- **다중 인스턴스 안전성**: 원자적 claim으로 중복 발행 방지

## 사용법

### 1. 애플리케이션에서 플러그인 로드

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()  # outbox와 sqlalchemy plugin을 자동 로드
    .scan()
    .start()
)
```

### 2. Use case에서 이벤트 발행

`IAsyncEventPublisher`로 발행된 이벤트는 자동으로 라우팅됩니다.

- `AbstractDomainEvent` → in-process dispatch
- `AbstractIntegrationEvent` → `IEventBus`(Outbox가 `@Primary`로 가로챔)

```python
from spakky.core.common.mutability import immutable
from spakky.core.stereotype.usecase import UseCase
from spakky.data.aspects.transactional import Transactional
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.event_publisher import IAsyncEventPublisher


@immutable
class OrderCreatedEvent(AbstractIntegrationEvent):
    order_id: int
    customer_id: int


@UseCase()
class CreateOrderUseCase:
    def __init__(self, event_publisher: IAsyncEventPublisher) -> None:
        self._event_publisher = event_publisher

    @Transactional()
    async def execute(self, command: CreateOrderCommand) -> Order:
        order = Order.create(...)
        # 이벤트는 order와 같은 transaction에 저장됨
        await self._event_publisher.publish(
            OrderCreatedEvent(order_id=order.id, customer_id=command.customer_id)
        )
        return order
```

### 3. 환경변수로 설정

| 변수                                  | 기본값 | 설명                     |
| ----------------------------------------- | ------- | ------------------------------- |
| `SPAKKY_OUTBOX__POLLING_INTERVAL_SECONDS` | `1.0`   | Relay polling interval          |
| `SPAKKY_OUTBOX__BATCH_SIZE`               | `100`   | batch당 message 수              |
| `SPAKKY_OUTBOX__MAX_RETRY_COUNT`          | `5`     | 포기 전 최대 retry 횟수    |
| `SPAKKY_OUTBOX__CLAIM_TIMEOUT_SECONDS`    | `300.0` | crash recovery용 claim 만료 |

## 구성 요소

| 구성 요소                                                            | 설명                                                              |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `IOutboxStorage` / `IAsyncOutboxStorage`                             | Outbox message storage port                                              |
| `OutboxEventBus` / `AsyncOutboxEventBus`                             | Outbox pattern용 event bus 경계(`@Primary`가 `DirectEventBus` 대체) |
| `OutboxRelayBackgroundService` / `AsyncOutboxRelayBackgroundService` | background relay service(polling 및 send)                                 |
| `OutboxConfig`                                                       | 환경변수 기반 설정                                  |
| `OutboxMessage`                                                      | Outbox message model                                                     |

### 커스텀 Storage 구현

custom storage backend를 구현하려면 다음 interface를 구현합니다.

```python
from spakky.outbox.ports.storage import IAsyncOutboxStorage
from spakky.outbox.common.message import OutboxMessage

class MyCustomStorage(IAsyncOutboxStorage):
    async def save(self, message: OutboxMessage) -> None:
        # 현재 transaction 안에서 저장
        ...

    async def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
        # pending message를 atomic claim 후 반환
        ...

    async def mark_published(self, message_id: UUID) -> None:
        ...

    async def increment_retry(self, message_id: UUID) -> None:
        ...
```

## 라이선스

MIT License
