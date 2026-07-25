# Spakky Kafka

> [Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 Apache Kafka 플러그인입니다.
> Event transport, consumer lifecycle, tracing/auth metadata propagation을 Kafka boundary에 연결합니다.

## 설치

```bash
pip install spakky-kafka
```

또는 Spakky extra로 설치합니다:

```bash
pip install spakky[kafka]
```

`IAsyncEventPublisher`와 함께 쓰는 Kafka 이벤트 서비스라면 event core까지 포함하는
`spakky[events-kafka]`를 권장합니다.

## 설정

`SPAKKY_KAFKA__` prefix를 가진 환경변수를 설정합니다:

```bash
export SPAKKY_KAFKA__GROUP_ID="my-consumer-group"
export SPAKKY_KAFKA__CLIENT_ID="my-app"
export SPAKKY_KAFKA__BOOTSTRAP_SERVERS="localhost:9092"
export SPAKKY_KAFKA__AUTO_OFFSET_RESET="earliest"  # earliest, latest, none
```

### SASL 인증 (선택)

```bash
export SPAKKY_KAFKA__SECURITY_PROTOCOL="SASL_SSL"
export SPAKKY_KAFKA__SASL_MECHANISM="PLAIN"
export SPAKKY_KAFKA__SASL_USERNAME="username"
export SPAKKY_KAFKA__SASL_PASSWORD="password"
```

### Topic 설정 (선택)

```bash
export SPAKKY_KAFKA__NUMBER_OF_PARTITIONS="3"
export SPAKKY_KAFKA__REPLICATION_FACTOR="1"
```

### 처리 실패 메시지 설정 (선택)

```bash
export SPAKKY_KAFKA__DEAD_LETTER_TOPIC_SUFFIX=".dlt"
export SPAKKY_KAFKA__MAX_HANDLER_RETRIES="0"
export SPAKKY_KAFKA__DEAD_LETTER_DELIVERY_TIMEOUT="10.0"
```

## 전달 의미 (at-least-once)

`KafkaConnectionConfig`는 producer 설정과 consumer 설정을 분리하여 각각의 안전한
기본값을 프레임워크가 고정합니다. 환경변수로 덮어쓸 수 있는 항목이 아닙니다.

| 속성 | 대상 | 고정 값 | 결과 |
|------|------|--------|------|
| `producer_configuration_dict` | `confluent_kafka.Producer` (이벤트 발행 + dead-letter 발행) | `enable.idempotence=true`, `acks=all` | 한 producer 세션의 재시도가 중복 발행·파티션 내 재정렬을 만들지 않고, 승인된 이벤트가 파티션 리더 장애를 견딤 |
| `async_producer_configuration_dict` | `aiokafka.AIOKafkaProducer` | `enable_idempotence=True`, `acks="all"` | 같은 값을 aiokafka 키 이름으로 표현 |
| `consumer_configuration_dict` | `confluent_kafka.Consumer`, `AIOConsumer` | `enable.auto.commit=false` | offset이 핸들러 결과에 따라서만 전진 |
| `connection_configuration_dict` | `AdminClient` 및 위 3종의 공통 기반 | `client.id`, `bootstrap.servers`, SASL/TLS | 클러스터 접속 정보만 담음 |

`AsyncKafkaEventTransport.send`는 호출마다 producer를 새로 만들어 닫으므로, 비동기 발행
경로의 멱등 보장 범위는 그 한 번의 `send`가 내부적으로 재시도하는 구간까지입니다. 서로
다른 `send` 호출 사이의 파티션 내 순서는 보장하지 않습니다.

Consumer는 등록된 핸들러가 끝난 뒤 그 메시지를 처리 완료로 볼지 다시 받을지 결정합니다.
`MessageOutcome`이 그 두 결정을 나타냅니다.

| 핸들러 결과 | `MessageOutcome` | offset 처리 |
|------------|------------------|------------|
| 성공 | `PROCESSED` | 커밋 후 다음 메시지로 진행 |
| 실패 → dead-letter 발행 성공 | `PROCESSED` | 커밋. 실패가 `.dlt` 토픽에 남았으므로 파티션을 막지 않음 |
| 실패 → dead-letter 발행 실패·미확인 | `RETRYABLE` | 커밋하지 않고 그 메시지로 `seek` 되감기 |
| 역직렬화 실패 | dead-letter 결과에 따름 | 위 두 줄과 같은 규칙 |
| AuthContext DENY / snapshot CHALLENGE | `PROCESSED` | warning 로그 후 커밋. 재시도해도 같은 결정임 |
| 본문 없는 메시지 | `PROCESSED` | warning 로그 후 커밋. 처리할 대상이 없음 |
| 검증 provider 장애 | (해당 없음) | 예외를 전파하여 consumer 루프를 중단. 커밋하지 않았으므로 재시작 시 그 메시지부터 다시 처리 |

**offset은 실패가 다른 곳에 저장된 뒤에만 전진합니다.** dead-letter 발행이 실패했는데
커밋해 버리면 그 이벤트의 마지막 사본이 사라집니다. 그래서 발행 실패는 커밋 대신 되감기로
이어집니다.

**커밋을 건너뛰는 것만으로는 재처리가 성립하지 않습니다.** `enable.auto.commit=false`는
브로커 커밋만 끄고 consumer의 소비 위치는 poll마다 전진합니다. 되감지 않으면 뒤따르는
메시지의 성공 커밋이 실패한 메시지의 offset을 지나쳐 버려 그 메시지는 rebalance나
재시작으로도 돌아오지 않습니다. `seek` 되감기가 재처리를 성립시키는 수단입니다.

전달 의미가 at-most-once에서 at-least-once로 바뀌었으므로 **같은 이벤트가 두 번 이상
전달될 수 있습니다.** 이벤트 핸들러는 멱등해야 합니다. 이미 처리한 이벤트 식별자를
저장하거나 upsert로 반영하는 방식이 필요합니다.

커밋과 되감기 실패는 로그로 남기고 삼킵니다. consumer 루프는 background service 스레드
(비동기는 asyncio 태스크)에서 돌기 때문에, 커밋 실패 예외를 전파하면 애플리케이션은 살아
있는 채로 모든 구독이 멈춥니다.

메시지 단위 동기 커밋은 브로커 왕복을 한 번씩 추가합니다. 처리량이 커밋 지연에 지배되는
워크로드라면 파티션 수를 늘려 consumer를 병렬화합니다.

## 사용법

### 이벤트 발행

```python
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.event_publisher import IEventPublisher
from spakky.core.pod.annotations.pod import Pod

@immutable
class UserCreatedEvent(AbstractIntegrationEvent):
    user_id: int
    email: str

@Pod()
class UserService:
    def __init__(self, publisher: IEventPublisher) -> None:
        self.publisher = publisher

    def create_user(self, email: str) -> User:
        user = User(email=email)
        self.publisher.publish(UserCreatedEvent(user_id=user.id, email=email))
        return user
```

### 이벤트 수신

```python
from spakky.event.stereotype.event_handler import EventHandler, on_event

@EventHandler()
class UserEventHandler:
    def __init__(self, notification_service: NotificationService) -> None:
        self.notification_service = notification_service

    @on_event(UserCreatedEvent)
    async def on_user_created(self, event: UserCreatedEvent) -> None:
        await self.notification_service.send_welcome_email(event.email)
```

### 비동기 변형

비동기 애플리케이션에서는 `IAsyncEventPublisher`를 사용합니다:

```python
from spakky.event.event_publisher import IAsyncEventPublisher

@Pod()
class AsyncUserService:
    def __init__(self, publisher: IAsyncEventPublisher) -> None:
        self.publisher = publisher

    async def create_user(self, email: str) -> User:
        user = User(email=email)
        await self.publisher.publish(UserCreatedEvent(user_id=user.id, email=email))
        return user
```

## 분산 트레이싱

`spakky-tracing`은 필수 의존성으로 자동 설치됩니다. `ITracePropagator`가 컨테이너에 등록되어 있으면 이벤트 발행/소비 시 `TraceContext`가 자동으로 전파됩니다.

- **발행 측**: `IEventTransport.send()` 시 현재 `TraceContext`를 Kafka 메시지 헤더에 주입합니다
- **소비 측**: 수신 메시지에서 `TraceContext`를 추출하여 자식 스팬을 생성합니다
- 헤더가 없으면 새로운 루트 트레이스를 시작합니다

## AuthContext 스냅샷 소비

`spakky-auth` 보호 decorator가 붙은 Kafka event handler는 raw bearer token을
받지 않습니다. Consumer는 사용자 handler 호출 직전에
`x-spakky-auth-context-snapshot` 또는 `spakky.auth.context_snapshot` Kafka header의
signed `AuthContextSnapshot`을 `IAuthContextSnapshotVerifier`로 검증하고,
`ApplicationContext`에 `AuthContext`를 seed합니다.

- snapshot 검증은 `KafkaPostProcessor`가 message별 `clear_context()`를 수행한 뒤,
  사용자 handler를 호출하기 전에 실행됩니다.
- missing, invalid, expired snapshot은 보호된 handler를 호출하지 않는 CHALLENGE
  fail-closed로 처리하며 Kafka consumer loop는 메시지를 처리 완료로 둡니다.
- 보호 요구사항 DENY도 handler 호출을 완료 처리하여 offset poison loop를 만들지
  않습니다.
- verifier provider unavailable은 ERROR로 전파되어 consumer route에서 삼키지 않고
  broker/runtime retry 정책에 맡깁니다.
- 기존 `traceparent` header와 event payload 역직렬화 의미는 그대로 유지됩니다.

## 처리 실패 메시지 (dead-letter)

핸들러 실패와 역직렬화 실패 메시지는 원본 topic 이름에 `dead_letter_topic_suffix`(기본
`.dlt`)를 붙인 topic으로 전달됩니다. 원본 본문과 key는 바이트 그대로 전달하고, 원본
header는 consumer가 읽은 문자열 형태로 함께 싣습니다(값이 없거나 UTF-8 문자열이 아닌
header는 제외). 재처리 도구가 본문을 열지 않고 판단할 수 있도록 원본 좌표와 예외
정보를 header로 덧붙입니다.

- `x-spakky-dead-letter-original-topic` / `-partition` / `-offset` / `-timestamp`: 원본 좌표
- `x-spakky-dead-letter-consumer-group`: 처리에 실패한 consumer group
- `x-spakky-dead-letter-exception-type` / `-exception-message`: 실패 원인

`max_handler_retries`를 0보다 크게 두면 dead-letter 전에 핸들러를 그 횟수만큼 다시
호출합니다. 재호출은 해당 이벤트의 모든 handler를 다시 실행하므로 handler 멱등성이
전제입니다. 역직렬화 실패는 재시도가 해결하지 못하므로 이 설정과 무관하게 즉시
dead-letter로 보냅니다.

dead-letter 발행은 `dead_letter_delivery_timeout`(기본 10초)까지만 배달을 기다립니다.
크기 제한 초과·producer 큐 포화·브로커 거절은 오류 로그를 남기고 consumer는 계속
폴링합니다. 비동기 경로에서 배달 확인이 시간 안에 오지 않은 경우는 확정 실패와 구분해
"unconfirmed"로 기록합니다 — 그 레코드는 나중에 배달될 수 있어 수동 재발행 시 중복이
생깁니다.

dead-letter topic은 consumer `initialize` 시점에 구독 topic과 함께 생성됩니다.

## 주요 기능

- **자동 topic 생성**: 이벤트 타입 이름을 기준으로 topic 생성 (dead-letter topic 포함)
- **at-least-once 전달**: 멱등 producer + 실패가 저장된 뒤에만 전진하는 명시적 offset 커밋
- **Dead-letter 경로**: 처리 실패 메시지를 원본 좌표·예외 header와 함께 `.dlt` topic으로 전달
- **파티션 키 라우팅**: `AbstractIntegrationEvent.partition_key`를 오버라이드하면 같은 키의 이벤트가 같은 파티션으로 가서 순서가 유지됩니다. 기본값 `None`은 라운드로빈 분산
- **동기/비동기 지원**: 동기 및 비동기 publisher/consumer 모두 지원
- **Background service 패턴**: consumer polling을 background service로 실행
- **Pydantic 직렬화**: 이벤트를 Pydantic으로 직렬화/역직렬화
- **Confluent Kafka client**: 안정적인 `confluent-kafka` library 기반
- **분산 트레이싱**: 서비스 간 trace 전파를 위한 `spakky-tracing` 통합

## 구성 요소

| 컴포넌트 | 설명 |
|-----------|-------------|
| `KafkaEventTransport` | 동기 event transport(`IEventTransport`) |
| `AsyncKafkaEventTransport` | 비동기 event transport(`IAsyncEventTransport`) |
| `KafkaEventConsumer` | 동기 event consumer(background service) |
| `AsyncKafkaEventConsumer` | 비동기 event consumer(background service) |
| `KafkaConnectionConfig` | 환경변수 기반 설정 |
| `DeadLetterHeaderKey` | dead-letter 메시지에 실리는 원본 좌표·예외 header 키 |
| `KafkaAuthBoundary` | signed `AuthContextSnapshot` 검증 및 `AuthContext` seeding |

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
