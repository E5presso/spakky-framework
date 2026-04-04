# Kafka 통합

`spakky-kafka`는 `IEventTransport` 인터페이스를 통해 Integration Event를 Apache Kafka로 전송하고, 백그라운드 Consumer로 수신합니다.

---

## 동작 원리

1. `@EventHandler`의 `@on_event` 메서드가 `KafkaPostProcessor`에 의해 Consumer에 자동 등록
2. Integration Event 발행 시 `KafkaEventTransport`가 Kafka 토픽으로 전송
3. `KafkaEventConsumer`가 백그라운드 서비스로 토픽을 소비하며 핸들러에 dispatch

---

## 설정

`KafkaConnectionConfig`는 `@Configuration`이므로 환경변수에서 자동 로딩됩니다.

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
import spakky.plugins.kafka
import apps

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(include={spakky.plugins.kafka.PLUGIN_NAME})
    .scan(apps)
    .start()
)
```

환경변수 예시:

```bash
export SPAKKY_KAFKA__GROUP_ID=my-consumer-group
export SPAKKY_KAFKA__CLIENT_ID=my-app
export SPAKKY_KAFKA__BOOTSTRAP_SERVERS=localhost:9092
export SPAKKY_KAFKA__AUTO_OFFSET_RESET=earliest
export SPAKKY_KAFKA__POLL_TIMEOUT=1.0
```

| 필드 | 환경변수 | 기본값 | 설명 |
|------|---------|--------|------|
| `group_id` | `SPAKKY_KAFKA__GROUP_ID` | (필수) | Consumer 그룹 ID |
| `client_id` | `SPAKKY_KAFKA__CLIENT_ID` | (필수) | Kafka 클라이언트 ID |
| `bootstrap_servers` | `SPAKKY_KAFKA__BOOTSTRAP_SERVERS` | (필수) | 부트스트랩 서버 주소 |
| `security_protocol` | `SPAKKY_KAFKA__SECURITY_PROTOCOL` | `None` | 보안 프로토콜 |
| `sasl_mechanism` | `SPAKKY_KAFKA__SASL_MECHANISM` | `None` | SASL 인증 메커니즘 |
| `sasl_username` | `SPAKKY_KAFKA__SASL_USERNAME` | `None` | SASL 사용자명 |
| `sasl_password` | `SPAKKY_KAFKA__SASL_PASSWORD` | `None` | SASL 비밀번호 |
| `number_of_partitions` | `SPAKKY_KAFKA__NUMBER_OF_PARTITIONS` | `1` | 토픽 파티션 수 |
| `replication_factor` | `SPAKKY_KAFKA__REPLICATION_FACTOR` | `1` | 토픽 복제 팩터 |
| `auto_offset_reset` | `SPAKKY_KAFKA__AUTO_OFFSET_RESET` | `earliest` | 오프셋 리셋 정책 |
| `poll_timeout` | `SPAKKY_KAFKA__POLL_TIMEOUT` | `1.0` | 폴링 타임아웃 (초) |

---

## 이벤트 발행

Integration Event를 발행하면 `EventPublisher`가 `IEventBus`를 통해 `KafkaEventTransport`로 전달합니다.

```python
from uuid import UUID
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent

@immutable
class OrderPlacedEvent(AbstractIntegrationEvent):
    order_id: UUID
    total_amount: float
```

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
```

---

## 이벤트 수신

`@EventHandler`와 `@on_event`로 수신 핸들러를 정의합니다. `KafkaPostProcessor`가 자동으로 Consumer에 등록합니다.

```python
from spakky.event.stereotype.event_handler import EventHandler, on_event

@EventHandler()
class OrderEventHandler:
    @on_event(OrderPlacedEvent)
    async def on_order_placed(self, event: OrderPlacedEvent) -> None:
        print(f"주문 접수: {event.order_id}, 금액: {event.total_amount}")
```

토픽 이름은 이벤트 클래스의 `__name__`(예: `OrderPlacedEvent`)으로 자동 결정됩니다. 토픽이 존재하지 않으면 `number_of_partitions`와 `replication_factor` 설정값으로 자동 생성합니다.

---

## SASL 인증

프로덕션 환경에서 SASL 인증을 사용하려면:

```bash
export SPAKKY_KAFKA__SECURITY_PROTOCOL=SASL_SSL
export SPAKKY_KAFKA__SASL_MECHANISM=PLAIN
export SPAKKY_KAFKA__SASL_USERNAME=my-api-key
export SPAKKY_KAFKA__SASL_PASSWORD=my-api-secret
```

---

## 분산 트레이싱

`spakky-tracing`은 `spakky-kafka`의 필수 의존성입니다. 컨테이너에 `ITracePropagator`가 등록되어 있으면 메시지 헤더를 통해 `TraceContext`가 자동 전파됩니다.

- **발행 측**: `OutboxEventBus` 또는 `DirectEventBus`가 현재 `TraceContext`를 메시지 헤더에 주입
- **수신 측**: `KafkaEventConsumer`가 헤더에서 `TraceContext`를 추출하여 자식 span 생성
- 헤더가 없으면 새로운 루트 트레이스를 시작
- `ITracePropagator`가 컨테이너에 없으면 트레이싱은 비활성 상태로, 별도 에러 없이 동작합니다

별도 설정이나 코드 변경 없이, 플러그인 로드만으로 동작합니다.
