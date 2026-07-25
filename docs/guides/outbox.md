# Transactional Outbox

> `spakky-outbox`로 transaction 이후 Integration Event를 at-least-once로 전달하는 흐름을, 개념과 사용법으로 나누어 설명합니다.

`spakky-outbox`는 Transactional Outbox 패턴을 구현하여 Integration Event의 at-least-once 전달을 보장합니다. events·outbox·saga가 함께 동작하는 전체 그림은 [이벤트 기반 아키텍처 통합 가이드](event-driven.md)를 참고하세요.

---

## 개념

### 해결하는 문제 — 이중 쓰기

DB 트랜잭션을 commit한 뒤 별도로 브로커에 이벤트를 전송하면, 트랜잭션은 성공했는데 브로커 전송만 실패하는 순간 이벤트가 영구히 유실됩니다. 반대로 브로커 먼저 보내면 트랜잭션 rollback 시 "일어나지 않은 일"이 외부에 알려집니다. 두 저장소(DB·브로커)를 하나의 원자적 연산으로 묶을 수 없는 것이 이중 쓰기 문제입니다.

Outbox는 이벤트를 **비즈니스 데이터와 같은 DB 트랜잭션 안에서 Outbox 테이블에 저장**하고, 브로커 전송은 별도 폴링 프로세스로 분리해 이 문제를 해결합니다. DB commit 하나에 비즈니스 변경과 이벤트가 함께 남으므로 유실 구간이 사라집니다.

### 동작 원리

1. `OutboxEventBus`가 `@Primary`로 기본 `IEventBus`를 대체합니다.
2. Integration Event 발행 시 메시지 브로커 대신 Outbox 테이블에 저장합니다 (트랜잭션 내).
3. `OutboxRelayBackgroundService`가 주기적으로 Outbox 테이블을 폴링합니다.
4. 미전송 메시지를 `IEventTransport`(Kafka/RabbitMQ)를 통해 실제 전송합니다.
5. 전송 성공 시 메시지를 published 처리, 실패 시 재시도 카운트를 증가시킵니다.

### 폴링 → 전송 흐름

발행 측(UseCase 트랜잭션)과 전송 측(Relay 폴링)이 시간적으로 분리됩니다. Relay는 `fetch_pending`으로 미전송 메시지를 원자적으로 claim한 뒤 전송하고, 성공·실패에 따라 상태를 갱신합니다.

```mermaid
sequenceDiagram
  participant UseCase as "@Transactional UseCase"
  participant Bus as OutboxEventBus
  participant Storage as IOutboxStorage
  participant Relay as OutboxRelayBackgroundService
  participant Transport as IEventTransport
  participant Broker as 메시지 브로커

  UseCase->>Bus: publish(IntegrationEvent)
  Bus->>Storage: save(OutboxMessage)
  Note over UseCase,Storage: 같은 트랜잭션에서 commit
  loop polling_interval_seconds 주기
    Relay->>Storage: fetch_pending(batch_size, max_retry)
    Storage-->>Relay: 미전송 메시지 (claim)
    Relay->>Transport: send(event_name, payload, headers)
    alt 전송 성공
      Transport->>Broker: 메시지 전달
      Relay->>Storage: mark_published(id)
    else 전송 실패
      Relay->>Storage: increment_retry(id)
    end
  end
```

`OutboxMessage`는 이 흐름을 거치며 상태가 전이됩니다. `claimed_at`은 폴링이 메시지를 가져갈 때 잠금으로 찍히며, `claim_timeout_seconds`가 지나면 다른 폴링 사이클이 다시 claim할 수 있어(크래시 복구) 전송이 멈추지 않습니다.

```mermaid
stateDiagram-v2
  [*] --> Pending: save (트랜잭션 commit)
  Pending --> Claimed: fetch_pending (claimed_at 기록)
  Claimed --> Published: 전송 성공 → mark_published
  Claimed --> Pending: 전송 실패 → increment_retry
  Claimed --> Pending: claim_timeout 초과 (크래시 복구)
  Published --> [*]
```

---

## 사용법

### 설정

`OutboxConfig`는 `@Configuration`이므로 환경변수에서 자동 로딩됩니다.

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
import spakky.outbox
import spakky.plugins.rabbitmq  # 또는 spakky.plugins.kafka
import spakky.plugins.sqlalchemy
import apps

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(include={
        spakky.outbox.PLUGIN_NAME,
        spakky.plugins.sqlalchemy.PLUGIN_NAME,  # Outbox storage provider
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

### 이벤트 발행

코드 변경 없이 플러그인 로드만으로 동작합니다. 기존 `IAsyncEventPublisher.publish()` 호출이 그대로 Outbox를 통하게 됩니다.

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

### 핵심 컴포넌트

#### OutboxEventBus

`@Primary`로 등록되어 기본 `IEventBus` / `IAsyncEventBus`를 대체합니다. `send()` 호출 시 메시지를 직접 브로커로 전송하지 않고 `IOutboxStorage`에 저장합니다.

```python
from spakky.outbox.bus.outbox_event_bus import OutboxEventBus, AsyncOutboxEventBus
```

#### OutboxRelayBackgroundService

백그라운드 서비스로 실행되며, Outbox 테이블에서 미전송 메시지를 주기적으로 가져와 `IEventTransport`로 전송합니다.

```python
from spakky.outbox.relay.relay import (
    OutboxRelayBackgroundService,
    AsyncOutboxRelayBackgroundService,
)
```

#### IOutboxStorage

Outbox 메시지의 저장/조회/상태 변경을 담당하는 포트 인터페이스입니다.
`spakky-sqlalchemy`는 `spakky.contributions.spakky.outbox` contribution으로
SQLAlchemy 구현체와 Outbox table을 제공합니다.

```python
from spakky.outbox.ports.storage import IOutboxStorage, IAsyncOutboxStorage
```

| 메서드 | 설명 |
|--------|------|
| `save(message)` | 현재 트랜잭션 내에서 메시지 저장 |
| `fetch_pending(limit, max_retry)` | 미전송 메시지 조회 (잠금 포함) |
| `mark_published(message_id)` | 메시지를 전송 완료 처리 |
| `increment_retry(message_id)` | 재시도 카운트 증가 |

#### OutboxMessage

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
| `partition_key` | `str \| None` | 브로커 파티션을 고정하는 키. bus가 이벤트의 `partition_key`를 그대로 옮기며, `None`이면 라운드로빈 분산 |
| `created_at` | `datetime` | 생성 시각 |
| `published_at` | `datetime \| None` | 전송 완료 시각 |
| `retry_count` | `int` | 재시도 횟수 |
| `claimed_at` | `datetime \| None` | 잠금 시각 |

---

## 스키마 업그레이드 — `partition_key` 컬럼 추가

`spakky-sqlalchemy`의 `OutboxMessageTable`은 migration용 table metadata만 제공하고, 운영 스키마 적용은 사용자 migration이 소유합니다(`SchemaRegistry`). 따라서 이미 `spakky_event_outbox` 테이블이 배포된 환경을 이 버전으로 올릴 때는 컬럼 추가 DDL을 직접 실행해야 합니다.

```sql
ALTER TABLE spakky_event_outbox ADD COLUMN partition_key TEXT NULL;
```

DDL을 실행하지 않은 채 배포하면 다음 두 곳이 깨집니다.

| 위치 | 증상 |
|------|------|
| `IOutboxStorage.save()` | 존재하지 않는 컬럼을 참조하는 INSERT가 실패합니다. `save()`는 비즈니스 트랜잭션 안에서 호출되므로 **이벤트를 발행하는 모든 UseCase가 함께 롤백됩니다.** |
| `OutboxRelayBackgroundService` | `fetch_pending()`의 SELECT가 실패하고, 이 예외는 릴레이의 재시도 `try` 블록 밖에서 발생하므로 **릴레이 백그라운드 서비스가 종료됩니다.** |

컬럼의 `NULL` 허용은 "파티션 키 없음"(라운드로빈 발행)이라는 도메인 값을 표현하기 위한 것이며, 마이그레이션을 대신하지 않습니다. 기존 row는 DDL 적용 후 `partition_key`가 `NULL`이 되어 이전과 동일하게 라운드로빈으로 발행됩니다.

---

## 분산 트레이싱

`spakky-tracing`이 설치되면 `OutboxEventBus`가 현재 `TraceContext`를 메시지 헤더에 자동 주입합니다. Relay가 전송할 때 해당 헤더가 그대로 브로커 메시지에 포함되므로, 수신 측에서 트레이스 컨텍스트가 복원됩니다.

## 인증 컨텍스트 전파

`SPAKKY_AUTH_SNAPSHOT_PROPAGATION_ENABLED=true`가 설정되어 있고 현재 request/context scope에 `AuthContext`가 있으면 `OutboxEventBus` / `AsyncOutboxEventBus`는 Outbox message headers에 `spakky.auth.context_snapshot` metadata를 저장합니다. 이 값은 `IAuthContextSnapshotSigner`가 만든 signed `AuthContextSnapshot` envelope이며, raw bearer token은 저장하지 않습니다. 기존 `traceparent` header는 함께 보존됩니다.

---

## 다음 단계

- [이벤트 기반 아키텍처 통합 가이드](event-driven.md) — events·outbox·saga를 함께 쓰는 분산 워크플로우
- [이벤트 시스템](events.md) — 도메인/통합 이벤트 발행과 핸들러 등록
- [사가 오케스트레이션](saga.md) — 보상 기반 분산 트랜잭션과 Outbox 조합
