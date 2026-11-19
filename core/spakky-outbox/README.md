# spakky-outbox

> [Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 트랜잭셔널 Outbox 패턴 패키지입니다.
> `IEventBus`를 `@Primary` outbox bus로 교체해 이벤트 저장과 외부 전송을 분리합니다.

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
- **commit 직후 발행**: 메시지를 저장한 transaction이 실제로 commit되면 background relay가 바로 깨어나 외부 transport(Kafka, RabbitMQ)로 발행. rollback되었거나 commit하지 않은 transaction은 relay를 깨우지 않으며, 주기 읽기는 보내지 못한 메시지의 복구에 쓰임
- **멈추지 않는 relay**: 읽기 도중 DB 오류가 나도 로그를 남기고 계속 돎
- **실패한 claim 즉시 해제**: 보내지 못한 메시지는 claim을 바로 풀어 claim timeout을 기다리지 않고 다음 읽기에서 다시 발행
- **재시도 지원**: transport가 영구적이고 특정 레코드에 귀속되는 거부를 확정한 경우에만 설정 가능한 한도 내에서 재시도하며, connection·timeout·queue 등 transport 자체 장애는 메시지별 retry 예산을 소모하지 않음
- **다중 인스턴스 안전성**: 원자적 claim으로 중복 발행 방지
- **파티션 키 단위 순서 보전**: 파티션 키를 통째로 claim하고, 영구 거부되어 재시도 대기 중인 키의 후속 메시지를 보류
- **발행 포기 상태**: 재시도를 소진한 메시지를 `abandoned` 처리하여 키가 무기한 막히지 않게 함

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
| `SPAKKY_OUTBOX__POLLING_INTERVAL_SECONDS` | `1.0`   | 보내지 못한 메시지를 다시 읽는 복구 주기. commit된 메시지는 이 주기를 기다리지 않음 |
| `SPAKKY_OUTBOX__BATCH_SIZE`               | `100`   | batch당 message 수              |
| `SPAKKY_OUTBOX__MAX_RETRY_COUNT`          | `5`     | 포기 전 최대 retry 횟수    |
| `SPAKKY_OUTBOX__CLAIM_TIMEOUT_SECONDS`    | `300.0` | crash recovery용 claim 만료 |

## 구성 요소

| 구성 요소                                                            | 설명                                                              |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `IOutboxStorage` / `IAsyncOutboxStorage`                             | Outbox message storage port                                              |
| `OutboxEventBus` / `AsyncOutboxEventBus`                             | Outbox pattern용 event bus 경계(`@Primary`가 `DirectEventBus` 대체) |
| `OutboxRelayBackgroundService` / `AsyncOutboxRelayBackgroundService` | background relay service(commit 직후 깨어남 + 복구용 주기 읽기, send)        |
| `OutboxRelayWakeup`                                                  | bus가 저장한 메시지의 transaction이 commit되면 relay를 깨우는 framework 내부 신호. 애플리케이션은 호출하지 않음 |
| `OutboxConfig`                                                       | 환경변수 기반 설정                                  |
| `OutboxMessage`                                                      | Outbox message model                                                     |

`OutboxEventBus`와 `AsyncOutboxEventBus`는 메시지를 저장할 때 `DirectEventBus`와 같은 outbound metadata 정책을 사용합니다. 기존 tracing header는 보존하고, auth snapshot 전파가 활성화된 request-scope에서는 `spakky.auth.context_snapshot`에 signed `AuthContextSnapshot` envelope를 저장합니다. Raw bearer token은 Outbox headers에 저장하지 않습니다.

### 커스텀 Storage 구현

custom storage backend를 구현하려면 다음 interface를 구현합니다. `release_claim()`은 abstract method이므로 기존 custom storage도 구현해야 합니다.

```python
from spakky.outbox.ports.storage import IAsyncOutboxStorage
from spakky.outbox.common.message import OutboxMessage

class MyCustomStorage(IAsyncOutboxStorage):
    async def save(self, message: OutboxMessage) -> None:
        # 현재 transaction 안에서 저장
        ...

    async def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
        # pending message를 atomic claim 후 반환.
        # 파티션 키가 있는 메시지는 그 키에서 아직 발행되지도 포기되지도 않은
        # 가장 오래된 메시지를 함께 claim할 때만 넘긴다 — 그러지 않으면 릴레이
        # 인스턴스 둘이 같은 키를 병렬 발행하여 키가 보장하려던 순서를 잃는다.
        ...

    async def mark_published(self, message_id: UUID) -> None:
        ...

    async def increment_retry(self, message_id: UUID) -> None:
        ...

    async def mark_abandoned(self, message_id: UUID) -> None:
        # 재시도를 소진한 메시지를 발행 대기열에서 빼되 레코드는 남긴다.
        # 이 상태가 없으면 그 메시지가 같은 키의 후속 메시지를 영구히 막는다.
        ...

    async def release_claim(self, message: OutboxMessage) -> None:
        # 릴레이가 보내지 못한 메시지의 claim을 풀어 다음 읽기에서 다시 나가게 한다.
        # retry count는 그대로 두고, 발행 완료·발행 포기 메시지는 건드리지 않는다.
        # message.claimed_at이 저장된 claim과 같을 때만 푼다 — claim timeout 뒤
        # 다른 인스턴스가 다시 잡은 claim을 지우면 같은 메시지가 병렬로 나간다.
        ...

    async def purge_published(self, older_than: datetime) -> int:
        # published_at이 older_than보다 이른 발행 완료 메시지만 지우고 지운 수를 반환한다.
        # 미발행 메시지와 발행 포기 메시지는 지우지 않는다.
        ...
```

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
