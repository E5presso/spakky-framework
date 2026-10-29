# 이벤트 시스템 9.0 마이그레이션

9.0.0부터 인프로세스 Domain Event의 기본 구현은 `spakky-event`에서 선택적 플러그인인 `spakky-mediator`로 분리되었습니다. 로컬 이벤트를 처리하던 앱은 패키지 설치와 플러그인 선택을 추가해야 합니다.

## 패키지별 책임

| 패키지 | 책임 |
| --- | --- |
| `spakky-domain` | `AbstractDomainEvent`, `AbstractIntegrationEvent` 모델 |
| `spakky-event` | 발행·bus·transport·consumer·dispatcher 계약, publisher, 트랜잭션 이벤트 발행 Aspect, `@EventHandler`·`@on_event`, 제공자 검증 |
| `spakky-mediator` | `EventMediator`, `AsyncEventMediator`, Domain Event handler 자동 등록 |
| `spakky-kafka`, `spakky-rabbitmq` | 브로커 transport·consumer, Integration Event handler 자동 등록 |

`IEventPublisher` / `IAsyncEventPublisher`와 이벤트 모델·stereotype의 import 경로는 유지됩니다. Domain Event는 dispatcher로, Integration Event는 bus로 보내는 타입 기반 라우팅도 유지됩니다.

## 1. 로컬 이벤트 제공자 설치

Domain Event를 로컬에서 처리하는 앱에 mediator를 추가합니다.

```bash
uv add 'spakky-mediator>=9.0.0'
# 또는 코어 패키지의 명시적인 extra 사용
uv add 'spakky[mediator]>=9.0.0'
```

`spakky-mediator`는 `spakky-event`를 의존성으로 설치합니다. `spakky[event]`, `spakky[events-kafka]`, `spakky[events-rabbitmq]`, `spakky[event-driven]`은 mediator를 포함하지 않습니다. `spakky[full]`에는 mediator가 포함됩니다.

브로커로 Integration Event만 발행·소비하는 앱에는 mediator 설치가 필요하지 않습니다.

## 2. 플러그인 선택에 mediator 추가

`load_plugins(include={...})`를 사용하는 앱은 기존 선택 목록에 `spakky.plugins.mediator.PLUGIN_NAME`을 추가합니다. 다음은 이벤트 관련 선택 목록의 예시입니다.

```python
import spakky.data
import spakky.event
import spakky.plugins.mediator
import spakky.tracing
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

app = SpakkyApplication(ApplicationContext()).load_plugins(include={
    spakky.data.PLUGIN_NAME,
    spakky.event.PLUGIN_NAME,
    spakky.plugins.mediator.PLUGIN_NAME,
    spakky.tracing.PLUGIN_NAME,
})
```

이 예시는 플러그인 선택 단계입니다. 트랜잭션 provider와 애플리케이션 Pod 등록·스캔은 기존 앱 설정대로 이어서 구성한 뒤 `start()`를 호출합니다. SQLAlchemy·Kafka·RabbitMQ 등을 이미 사용한다면 해당 플러그인도 선택 목록에 유지합니다.

`load_plugins()`를 인자 없이 호출하면 설치된 모든 플러그인을 로드하므로 mediator 설치 후 별도의 include 변경은 필요하지 않습니다. 서비스에서 사용할 제공자만 로드하려면 `include`로 선택합니다.

## 3. 구체 구현 import 변경

| 8.x import | 9.0.0 import |
| --- | --- |
| `spakky.event.mediator.EventMediator` | `spakky.plugins.mediator.mediator.EventMediator` |
| `spakky.event.mediator.AsyncEventMediator` | `spakky.plugins.mediator.mediator.AsyncEventMediator` |
| `spakky.event.mediator.domain_event_mediator` | `spakky.plugins.mediator.mediator` |
| `spakky.event.post_processor.EventHandlerRegistrationPostProcessor` | `spakky.plugins.mediator.post_processor.EventHandlerRegistrationPostProcessor` |

```python
from spakky.plugins.mediator.mediator import AsyncEventMediator, EventMediator
from spakky.plugins.mediator.post_processor import EventHandlerRegistrationPostProcessor
```

일반 애플리케이션은 기존 `spakky.event.event_publisher`의 publisher 인터페이스를 계속 주입받으면 됩니다. `spakky.event.post_processor`에는 등록기 대신 `EventHandlerProviderValidationPostProcessor`가 남습니다. 이 후처리기는 handler에 필요한 제공자가 있는지 검증합니다.

## 4. handler 종류에 맞는 제공자 사용

`@EventHandler`와 `@on_event` 선언은 두 이벤트 종류 모두에 사용합니다. 자동 등록은 이벤트 종류별 플러그인이 담당하며, 일반 메서드는 동기 consumer에, `async def`는 비동기 consumer에 등록합니다.

| 이벤트 종류 | 등록 담당 | Consumer 계약 (`spakky.event.event_consumer`) |
| --- | --- | --- |
| Domain Event | `spakky-mediator` | `IDomainEventConsumer` / `IAsyncDomainEventConsumer` |
| Integration Event | Kafka/RabbitMQ 플러그인 | `IIntegrationEventConsumer` / `IAsyncIntegrationEventConsumer` |

mediator와 브로커를 함께 사용하는 앱은 두 제공자를 모두 선택합니다. 플러그인 후처리기는 각 역할의 consumer에 등록하므로 전역 `IEventConsumer` 바인딩으로 한쪽을 고를 필요가 없습니다. 애플리케이션에서 consumer를 직접 주입받는 경우에도 역할별 계약을 사용합니다. 기존 `IEventConsumer` / `IAsyncEventConsumer`는 공통 기반 계약으로 유지됩니다.

## 제공자 누락 오류 확인

| 상황 | 오류 |
| --- | --- |
| 선언한 handler의 domain/integration·sync/async 역할에 맞는 consumer 없이 기동 | `EventHandlerProviderUnavailableError` |
| dispatcher 없이 Domain Event 발행 | `DomainEventDispatcherUnavailableError` |
| 기본 `DirectEventBus` 경로에서 transport 없이 Integration Event 발행 | `IntegrationEventTransportUnavailableError` |

위 오류는 `spakky.event.error`에 정의됩니다. handler를 선언하지 않은 event-only 앱은 로컬·브로커 consumer 없이 기동할 수 있지만, 실제 발행에는 이벤트 종류에 맞는 제공자가 필요합니다. Outbox를 사용하는 앱은 Integration Event를 storage에 기록한 뒤 Relay가 transport로 전달하는 별도 경로를 사용합니다.

로컬 mediator는 일반 handler 예외를 로그로 남기고 다음 handler를 실행합니다. `EventDeferredError`는 호출자에게 전파하며, 로컬 재시도 큐를 만들지 않습니다.

## 관련 문서

- [이벤트 시스템](events.md) — handler 작성과 발행 설정
- [spakky-mediator API](../api/plugins/spakky-mediator.md) — 구현체와 등록기
- [ADR-0022](../adr/0022-optional-domain-event-mediator-provider.md) — 분리 결정과 제공자 경계
