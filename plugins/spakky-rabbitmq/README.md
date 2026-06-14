# Spakky RabbitMQ

> [Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 RabbitMQ 플러그인입니다.
> Event transport, consumer lifecycle, tracing/auth metadata propagation을 RabbitMQ boundary에 연결합니다.

## 설치

```bash
pip install spakky-rabbitmq
```

또는 Spakky extra로 설치합니다:

```bash
pip install spakky[rabbitmq]
```

`IAsyncEventPublisher`와 함께 쓰는 RabbitMQ 이벤트 서비스라면 event core까지 포함하는
`spakky[events-rabbitmq]`를 권장합니다.

## 설정

`SPAKKY_RABBITMQ__` prefix를 가진 환경변수를 설정합니다:

```bash
export SPAKKY_RABBITMQ__USE_SSL="false"
export SPAKKY_RABBITMQ__HOST="localhost"
export SPAKKY_RABBITMQ__PORT="5672"
export SPAKKY_RABBITMQ__USER="guest"
export SPAKKY_RABBITMQ__PASSWORD="guest"
export SPAKKY_RABBITMQ__EXCHANGE_NAME="my-exchange"  # Optional
export SPAKKY_RABBITMQ__AUTH_CHALLENGE_ACTION="ack"
export SPAKKY_RABBITMQ__AUTH_DENY_ACTION="ack"
export SPAKKY_RABBITMQ__AUTH_ERROR_ACTION="nack_requeue"
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

- **발행 측**: `IEventTransport.send()` 시 현재 `TraceContext`를 메시지 헤더에 주입합니다
- **소비 측**: 수신 메시지에서 `TraceContext`를 추출하여 자식 스팬을 생성합니다
- 헤더가 없으면 새로운 루트 트레이스를 시작합니다

## 인증/인가 snapshot 수신

`spakky-auth`의 보호 decorator가 붙은 RabbitMQ event handler는 메시지 header의 signed `AuthContextSnapshot`을 검증한 뒤 `ApplicationContext`에 `AuthContext`를 seed합니다. seed 시점은 handler wrapper가 integration context를 `clear_context()`로 정리한 직후이며, 사용자 handler 호출 전입니다.

- 지원 header: `spakky.auth.context_snapshot`, `x-spakky-auth-context-snapshot`
- missing, invalid, expired snapshot: `CHALLENGE` decision으로 fail-closed
- protected handler의 `DENY`: configured ack/nack policy로 fail-closed
- verifier provider unavailable: `ERROR` decision이며 기본 retryable policy(`nack_requeue`) 적용
- event payload와 기존 trace header 의미는 변경하지 않습니다

인증 실패 시 message 처리 정책은 다음 환경변수로 조정합니다.

| 필드 | 환경변수 | 기본값 | 설명 |
|------|---------|--------|------|
| `auth_challenge_action` | `SPAKKY_RABBITMQ__AUTH_CHALLENGE_ACTION` | `ack` | missing/invalid/expired snapshot 처리 |
| `auth_deny_action` | `SPAKKY_RABBITMQ__AUTH_DENY_ACTION` | `ack` | protected handler DENY 처리 |
| `auth_error_action` | `SPAKKY_RABBITMQ__AUTH_ERROR_ACTION` | `nack_requeue` | verifier/provider ERROR 처리 |

가능한 값은 `ack`, `nack_requeue`, `nack_drop`입니다. 기본값은 CHALLENGE/DENY를 ack하여 poison-loop를 피하고, ERROR만 requeue하여 일시적 provider 장애를 재시도합니다.

## 주요 기능

- **자동 queue 선언**: 이벤트 타입 이름을 기준으로 durable queue 생성
- **동기/비동기 지원**: 동기 및 비동기 publisher/consumer 모두 지원
- **Background service 패턴**: consumer polling을 background service로 실행
- **Pydantic 직렬화**: 이벤트를 Pydantic으로 직렬화/역직렬화
- **Exchange 라우팅**: pub/sub 메시지 패턴을 위한 선택적 exchange
- **SSL 지원**: AMQPS protocol 기반 보안 연결
- **분산 트레이싱**: 서비스 간 trace 전파를 위한 `spakky-tracing` 통합
- **인증/인가 보호 경계**: signed `AuthContextSnapshot` 검증 및 protected handler fail-closed 처리

## 구성 요소

| 컴포넌트 | 설명 |
|-----------|-------------|
| `RabbitMQEventTransport` | 동기 event transport(`IEventTransport`) |
| `AsyncRabbitMQEventTransport` | 비동기 event transport(`IAsyncEventTransport`) |
| `RabbitMQEventConsumer` | 동기 event consumer(background service) |
| `AsyncRabbitMQEventConsumer` | 비동기 event consumer(background service) |
| `RabbitMQConnectionConfig` | 환경변수 기반 설정 |
| `RabbitMQAuthBoundary` | signed `AuthContextSnapshot` 검증 및 `AuthContext` seed helper |

## 에러 처리

- **`InvalidMessageError`**: 필수 metadata(`consumer_tag` 또는 `delivery_tag`)가 없는 message에서 발생
- 보호된 handler 인증/인가 실패는 handler를 호출하지 않고 ack/nack 정책으로 fail-closed 처리됩니다

## 라이선스

MIT License
