# Spakky Kafka

[Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 Apache Kafka 플러그인입니다.

## 설치

```bash
pip install spakky-kafka
```

또는 Spakky extra로 설치합니다:

```bash
pip install spakky[kafka]
```

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

## 주요 기능

- **자동 topic 생성**: 이벤트 타입 이름을 기준으로 topic 생성
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

## 라이선스

MIT License
