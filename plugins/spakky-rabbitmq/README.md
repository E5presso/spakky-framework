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
export SPAKKY_RABBITMQ__DECLARE_DEFAULT_QUEUE="true"  # Optional
export SPAKKY_RABBITMQ__RETRY__MAX_ATTEMPTS="3"      # Optional
export SPAKKY_RABBITMQ__RETRY__INITIAL_INTERVAL="1.0"
export SPAKKY_RABBITMQ__RETRY__MULTIPLIER="2.0"
export SPAKKY_RABBITMQ__RETRY__MAX_INTERVAL="60.0"
export SPAKKY_RABBITMQ__RETRY__MODE="blocking"       # blocking | delayed
export SPAKKY_RABBITMQ__AUTH_CHALLENGE_ACTION="ack"
export SPAKKY_RABBITMQ__AUTH_DENY_ACTION="ack"
export SPAKKY_RABBITMQ__AUTH_ERROR_ACTION="nack_requeue"
```

| 필드 | 환경변수 | 기본값 | 설명 |
|------|---------|--------|------|
| `exchange_name` | `SPAKKY_RABBITMQ__EXCHANGE_NAME` | `None` | 발행·바인딩에 쓰는 exchange. 이름 있는 구독자를 쓰려면 필수 |
| `declare_default_queue` | `SPAKKY_RABBITMQ__DECLARE_DEFAULT_QUEUE` | `true` | 발행 시 이벤트 이름 큐(이름 없는 구독자의 큐)를 선언·바인딩할지 여부 |
| `retry.max_attempts` | `SPAKKY_RABBITMQ__RETRY__MAX_ATTEMPTS` | `1` | 첫 시도를 포함한 총 시도 횟수 |
| `retry.initial_interval` | `SPAKKY_RABBITMQ__RETRY__INITIAL_INTERVAL` | `0.0` | 두 번째 시도 전 대기(초) |
| `retry.multiplier` | `SPAKKY_RABBITMQ__RETRY__MULTIPLIER` | `2.0` | 실패할 때마다 대기에 곱하는 배수 |
| `retry.max_interval` | `SPAKKY_RABBITMQ__RETRY__MAX_INTERVAL` | `60.0` | 대기의 상한(초) |
| `retry.mode` | `SPAKKY_RABBITMQ__RETRY__MODE` | `blocking` | `blocking`(순서 유지) 또는 `delayed`(대기 큐 사용) |

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

### 구독자

`@EventHandler(subscriber=...)`로 구독자를 지정하면 구독자마다 전용 큐를 갖고 같은 이벤트를 각자 한 부씩 받습니다. 재시도와 dead-letter도 구독자별로 따로 관리되어, 한 구독자의 실패가 다른 구독자를 막지 않습니다.

```python
@EventHandler(subscriber="billing")
class BillingHandler:
    @on_event(UserCreatedEvent)
    async def open_account(self, event: UserCreatedEvent) -> None: ...


@EventHandler(subscriber="mailing")
class MailingHandler:
    @on_event(UserCreatedEvent)
    async def send_welcome(self, event: UserCreatedEvent) -> None: ...
```

| 자원 | 이름 없는 구독자 | 구독자 `billing` |
|------|------------------|------------------|
| 소비 큐 | `<event_name>` | `<event_name>.billing` |
| 대기 큐 (`retry.mode=delayed`일 때만) | `<event_name>.retry` | `<event_name>.billing.retry` |
| dead-letter 큐 | `<event_name>.dlq` | `<event_name>.billing.dlq` |

- 이름 있는 구독자는 `exchange_name`이 필수입니다. 없으면 기동 시 `SubscriberExchangeRequiredError`가 납니다.
- 구독자 큐는 Consumer가 기동할 때 선언·바인딩되므로, 소비 서비스를 발행 서비스보다 먼저 배포하세요.
- 어떤 이벤트의 소비자가 모두 이름 있는 구독자라면, 발행 서비스에서 `SPAKKY_RABBITMQ__DECLARE_DEFAULT_QUEUE=false`로 이벤트 이름 큐 선언을 끄세요. 켜 두면 아무도 소비하지 않는 큐에 메시지가 쌓입니다.
- 한 구독(구독자와 이벤트 타입의 쌍)의 핸들러는 모두 동기이거나 모두 비동기여야 합니다.

### 재시도와 dead-letter

한 구독자 안에서 핸들러 하나가 실패해도 나머지는 모두 실행하고, 재시도는 아직 성공하지 못한 핸들러만 다시 실행합니다. `retry.max_attempts`를 다 쓰면 메시지를 그 구독자의 dead-letter 큐로 옮깁니다.

| `retry.mode` | 동작 |
|--------------|------|
| `blocking` (기본) | 메시지를 ack하지 않은 채 기다렸다가 다시 전달합니다. 큐마다 prefetch 1을 설정해 구독자 큐 안의 순서를 지킵니다. 진행 상태는 프로세스 메모리에 있어, 재시작하면 첫 시도부터 다시 실행합니다 |
| `delayed` | 재시도 상태를 헤더에 실은 사본을 `<소비 큐>.retry`에 넣고 원본을 ack합니다. 사본은 지연(TTL)이 지나면 그 구독자의 소비 큐로만 돌아옵니다. 순서는 보장하지 않습니다 |

- `AbstractNonRetryableEventError`를 상속한 예외와 역직렬화할 수 없는 payload는 재시도 없이 dead-letter 큐로 갑니다.
- `EventDeferredError(retry_after)`는 시도 횟수를 세지 않고 기다렸다가 다시 전달합니다.
- dead-letter·재시도 사본은 브로커의 publisher confirm을 받은 뒤에만 원본을 ack합니다. 확인되지 않으면 원본을 requeue합니다.
- `delayed`의 대기 큐는 구독자마다 하나이고 메시지별 TTL을 씁니다. RabbitMQ는 큐의 맨 앞 메시지만 만료시키므로, 지연이 긴 메시지가 앞에 있으면 뒤의 메시지는 설정한 지연보다 더 기다릴 수 있습니다.

dead-letter 메시지는 원래 본문과 문자열 헤더에 다음 헤더를 더해 저장합니다.

| 헤더 | 내용 |
|------|------|
| `x-spakky-dead-letter-original-destination` | 원래 발행된 이벤트 이름 |
| `x-spakky-dead-letter-subscriber` | 구독자 이름(이름 없는 구독자는 빈 문자열) |
| `x-spakky-dead-letter-failures` | 실패한 핸들러별 이름·예외 종류·메시지·재시도 가능 여부(JSON) |
| `x-spakky-dead-letter-attempts` | 시도 횟수 |
| `x-spakky-dead-letter-failed-at` | 마지막 시도가 끝난 시각(ISO 8601) |

### Redrive

Consumer는 `IEventRedriver` / `IAsyncEventRedriver`를 구현합니다. Redrive는 dead letter를 남긴 구독자에게만 전달하고, 실패로 기록된 핸들러만 실행합니다.

```python
from spakky.event.redrive import IAsyncEventRedriver

@Pod()
class BillingRecovery:
    def __init__(self, redriver: IAsyncEventRedriver) -> None:
        self.redriver = redriver

    async def run(self) -> None:
        result = await self.redriver.redrive(
            UserCreatedEvent, subscriber="billing", limit=100
        )
        print(result.succeeded, result.failed)
```

성공한 dead letter는 큐에서 지워지고, 다시 실패한 것은 호출이 끝날 때 그대로 큐에 되돌려집니다. 호출마다 dead letter당 한 번만 시도합니다.

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

- **자동 queue 선언**: 이벤트 이름과 구독자 이름을 기준으로 durable queue 생성
- **구독자별 독립 소비**: 구독자마다 전용 큐·재시도·dead-letter 큐
- **재시도와 dead-letter**: `RetryPolicy` 기반 `blocking`/`delayed` 재시도, 실패 메타데이터가 담긴 dead-letter, redrive
- **동기/비동기 지원**: 동기 및 비동기 publisher/consumer 모두 지원
- **Background service 패턴**: consumer polling을 background service로 실행
- **Pydantic 직렬화**: 이벤트를 Pydantic으로 직렬화/역직렬화
- **Exchange 라우팅**: pub/sub 메시지 패턴을 위한 선택적 exchange
- **파티션 키 미사용**: `AbstractIntegrationEvent.partition_key`는 transport 인터페이스 계약상 전달되지만 RabbitMQ 라우팅에는 **사용되지 않습니다**. RabbitMQ에는 파티션 개념이 없고 단일 queue는 이미 FIFO 순서이므로, 이 값을 오버라이드해도 발행 결과가 달라지지 않습니다
- **SSL 지원**: AMQPS protocol 기반 보안 연결
- **분산 트레이싱**: 서비스 간 trace 전파를 위한 `spakky-tracing` 통합
- **인증/인가 보호 경계**: signed `AuthContextSnapshot` 검증 및 protected handler fail-closed 처리

## 구성 요소

| 컴포넌트 | 설명 |
|-----------|-------------|
| `RabbitMQEventTransport` | 동기 event transport(`IEventTransport`) |
| `AsyncRabbitMQEventTransport` | 비동기 event transport(`IAsyncEventTransport`) |
| `RabbitMQEventConsumer` | 동기 event consumer(background service, `IEventRedriver`) |
| `AsyncRabbitMQEventConsumer` | 비동기 event consumer(background service, `IAsyncEventRedriver`) |
| `RabbitMQSubscriptionQueues` | 구독자의 소비·대기·dead-letter 큐 이름 계산 |
| `RabbitMQConnectionConfig` | 환경변수 기반 설정 |
| `RabbitMQAuthBoundary` | signed `AuthContextSnapshot` 검증 및 `AuthContext` seed helper |

## 에러 처리

- **`InvalidMessageError`**: 필수 metadata(`consumer_tag` 또는 `delivery_tag`)가 없는 message에서 발생
- **`SubscriberExchangeRequiredError`**: `exchange_name` 없이 이름 있는 구독자를 등록하면 기동 시 발생
- 핸들러 예외는 Consumer 밖으로 전파되지 않고 재시도·dead-letter 규칙으로 처리됩니다
- 보호된 handler 인증/인가 실패는 handler를 호출하지 않고 ack/nack 정책으로 fail-closed 처리됩니다. `ack`는 그 handler만 건너뛰고, `nack_requeue`는 전달을 중단하고 메시지를 requeue하며, `nack_drop`은 나머지 handler가 끝난 뒤 메시지를 requeue 없이 거부합니다

## 이전 버전에서 달라진 점

- `malformed_payload_action`(`SPAKKY_RABBITMQ__MALFORMED_PAYLOAD_ACTION`) 설정이 제거되었습니다. 역직렬화할 수 없는 payload는 항상 dead-letter 큐로 갑니다.
- 핸들러 예외가 Consumer 밖으로 전파되지 않습니다. `retry` 설정에 따라 재시도하고, 소진되면 `<소비 큐>.dlq`로 옮긴 뒤 ack합니다.
- 기본 모드(`blocking`)에서 큐마다 prefetch 1을 설정합니다. 비동기 Consumer가 한 큐의 메시지를 동시에 처리하던 이전 동작이 필요하면 `retry.mode=delayed`를 쓰세요.
- `exchange_name`이 있으면 Consumer도 exchange를 선언하고 자신의 큐를 바인딩합니다.
- `register()`가 `subscriber`, `handler_name` 키워드 인자를 받습니다. Consumer의 `handlers`, `type_lookup`, `type_adapters` 속성은 없어졌습니다.
- aspect가 적용되어 AOP proxy가 된 `@EventHandler`의 핸들러도 등록됩니다.

상세 동작은 저장소의 `docs/guides/rabbitmq.md`(RabbitMQ 통합 가이드)를 참고하세요.

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

### 로컬 이벤트 제공자와 함께 사용하기

RabbitMQ consumer는 integration 전용 역할을 제공하며 자신의 구체 consumer로 handler를
등록합니다. 로컬 domain handler는 별도 `spakky-mediator` 플러그인을 명시적으로 선택합니다.
