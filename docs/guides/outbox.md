# Transactional Outbox

`spakky-outbox`는 Transactional Outbox 패턴을 구현하여 Integration Event의 at-least-once 전달을 보장합니다.

---

## 동작 원리

1. `OutboxEventBus`가 `@Primary`로 기본 `IEventBus`를 대체
2. Integration Event 발행 시 메시지 브로커 대신 Outbox 테이블에 저장 (트랜잭션 내)
3. `OutboxRelayBackgroundService`가 주기적으로 Outbox 테이블을 폴링
4. 미전송 메시지를 `IEventTransport` (Kafka/RabbitMQ)를 통해 실제 전송
5. 전송 성공 시 메시지를 published 처리, 실패 시 재시도 카운트 증가

---

## 설정

`OutboxConfig`는 `@Configuration`이므로 환경변수에서 자동 로딩됩니다.

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
import spakky.outbox
import spakky.plugins.rabbitmq  # 또는 spakky.plugins.kafka
import apps

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(include={
        spakky.outbox.PLUGIN_NAME,
        spakky.plugins.rabbitmq.PLUGIN_NAME,  # Transport 플러그인 필수
    })
    .scan(apps)
    .start()
)
```

환경변수 예시:

```bash
export SPAKKY_OUTBOX__POLLING_INTERVAL_SECONDS=1.0
export SPAKKY_OUTBOX__BATCH_SIZE=100
export SPAKKY_OUTBOX__MAX_RETRY_COUNT=5
export SPAKKY_OUTBOX__CLAIM_TIMEOUT_SECONDS=300.0
```

| 필드 | 환경변수 | 기본값 | 설명 |
|------|---------|--------|------|
| `polling_interval_seconds` | `SPAKKY_OUTBOX__POLLING_INTERVAL_SECONDS` | `1.0` | 폴링 주기 (초) |
| `batch_size` | `SPAKKY_OUTBOX__BATCH_SIZE` | `100` | 배치당 처리 메시지 수 |
| `max_retry_count` | `SPAKKY_OUTBOX__MAX_RETRY_COUNT` | `5` | 최대 재시도 횟수 |
| `claim_timeout_seconds` | `SPAKKY_OUTBOX__CLAIM_TIMEOUT_SECONDS` | `300.0` | 메시지 잠금 타임아웃 (초) |

---

## 핵심 컴포넌트

### OutboxEventBus

`@Primary`로 등록되어 기본 `IEventBus` / `IAsyncEventBus`를 대체합니다. `send()` 호출 시 메시지를 직접 브로커로 전송하지 않고 `IOutboxStorage`에 저장합니다.

```python
from spakky.outbox.bus.outbox_event_bus import OutboxEventBus, AsyncOutboxEventBus
```

### OutboxRelayBackgroundService

백그라운드 서비스로 실행되며, Outbox 테이블에서 미전송 메시지를 주기적으로 가져와 `IEventTransport`로 전송합니다.

```python
from spakky.outbox.relay.relay import (
    OutboxRelayBackgroundService,
    AsyncOutboxRelayBackgroundService,
)
```

### IOutboxStorage

Outbox 메시지의 저장/조회/상태 변경을 담당하는 포트 인터페이스입니다. `spakky-sqlalchemy` 플러그인이 구현체를 제공합니다.

```python
from spakky.outbox.ports.storage import IOutboxStorage, IAsyncOutboxStorage
```

| 메서드 | 설명 |
|--------|------|
| `save(message)` | 현재 트랜잭션 내에서 메시지 저장 |
| `fetch_pending(limit, max_retry)` | 미전송 메시지 조회 (잠금 포함) |
| `mark_published(message_id)` | 메시지를 전송 완료 처리 |
| `increment_retry(message_id)` | 재시도 카운트 증가 |

### OutboxMessage

영속성에 독립적인 Outbox 메시지 모델입니다.

```python
from spakky.outbox.common.message import OutboxMessage
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | `UUID` | 메시지 고유 ID |
| `event_name` | `str` | 이벤트 이름 (라우팅 키) |
| `payload` | `bytes` | 직렬화된 이벤트 데이터 |
| `headers` | `dict[str, str]` | 메타데이터 헤더 (트레이스 전파 등) |
| `created_at` | `datetime` | 생성 시각 |
| `published_at` | `datetime \| None` | 전송 완료 시각 |
| `retry_count` | `int` | 재시도 횟수 |
| `claimed_at` | `datetime \| None` | 잠금 시각 |

---

## 사용 흐름

코드 변경 없이 플러그인 로드만으로 동작합니다.

```python
from spakky.core.stereotype.usecase import UseCase
from spakky.event.event_publisher import IAsyncEventPublisher

@UseCase()
class PlaceOrderUseCase:
    _publisher: IAsyncEventPublisher

    def __init__(self, publisher: IAsyncEventPublisher) -> None:
        self._publisher = publisher

    async def execute(self, order_id: UUID, total: float) -> None:
        event = OrderPlacedEvent(order_id=order_id, total_amount=total)
        await self._publisher.publish(event)
        # → OutboxEventBus가 Outbox 테이블에 저장 (트랜잭션 내)
        # → Relay가 주기적으로 Kafka/RabbitMQ로 전송
```

---

## 분산 트레이싱

`spakky-tracing`이 설치되면 `OutboxEventBus`가 현재 `TraceContext`를 메시지 헤더에 자동 주입합니다. Relay가 전송할 때 해당 헤더가 그대로 브로커 메시지에 포함되므로, 수신 측에서 트레이스 컨텍스트가 복원됩니다.
