# 이벤트 시스템

> 도메인 이벤트와 통합 이벤트를 발행하고 handler로 처리하는 기본 흐름을, 개념과 사용법으로 나누어 설명합니다.

도메인 이벤트를 자동으로 발행하고 핸들러에서 처리하는 이벤트 기반 아키텍처를 구축합니다. events·outbox·saga가 하나의 분산 워크플로우로 맞물리는 전체 그림은 [이벤트 기반 아키텍처 통합 가이드](event-driven.md)를 참고하세요.

---

## 개념

### 두 가지 이벤트 타입

| 이벤트 타입 | 전달 경로 | 용도 |
| --- | --- | --- |
| `AbstractDomainEvent` | 인프로세스 (`EventMediator`) | 같은 바운디드 컨텍스트 내 상태 변경 알림 |
| `AbstractIntegrationEvent` | 메시지 브로커 (`IEventBus` → RabbitMQ/Kafka) | 서비스/컨텍스트 간 통신 |

두 타입은 모두 `spakky.domain.models.event`에 정의되어 있고, `event_id: UUID`와 `timestamp: datetime`을 자동으로 가집니다. 정의 방법과 공통 속성, AggregateRoot의 이벤트 수집은 [이벤트 시스템 심화](../event-system.md)에서 다룹니다.

### 발행 라우팅

`IEventPublisher.publish()`는 단일 발행 진입점입니다. 이벤트 타입에 따라 인프로세스 핸들러(`EventMediator`)와 브로커(`IEventBus`)로 자동 라우팅합니다. 사용자 코드는 `publish()` 한 번만 호출하면 됩니다.

```mermaid
graph TD
  UseCase["@UseCase + @Transactional"]:::app
  Handler["@EventHandler"]:::app

  subgraph Framework[Spakky Framework]
    subgraph Core[코어]
      Publisher["IEventPublisher"]:::core
      Bus["IEventBus"]:::core
    end
    Mediator["EventMediator (spakky-mediator)"]:::plugin
    Transport["EventTransport (플러그인)"]:::plugin
  end

  Broker[메시지 브로커]:::external

  UseCase --> Publisher
  Publisher -->|"DomainEvent"| Mediator
  Mediator --> Handler
  Publisher -->|"IntegrationEvent"| Bus
  Bus --> Transport
  Transport --> Broker

  classDef app fill:#E3F2FD,stroke:#1565C0,color:#0D47A1
  classDef core fill:#E8F5E9,stroke:#2E7D32,color:#1B5E20
  classDef plugin fill:#FFF3E0,stroke:#EF6C00,color:#E65100
  classDef external fill:#ECEFF1,stroke:#546E7A,color:#263238
```

`@on_event` 핸들러는 `AbstractDomainEvent` 서브클래스에 대해서만 자동 등록됩니다. Integration Event는 핸들러 자동 등록 대상이 아니라, 브로커에서 수신해 transport consumer가 처리합니다.

---

## 사용법

### 이벤트 핸들러 정의

`@EventHandler`와 `@on_event`로 이벤트 핸들러를 선언합니다.

#### 동기 핸들러

```python
from spakky.event.stereotype.event_handler import EventHandler, on_event

@EventHandler()
class OrderEventHandler:
    @on_event(Order.Created)
    def on_order_created(self, event: Order.Created) -> None:
        print(f"주문 생성됨: {event.order_id}, 금액: {event.total_amount}")

    @on_event(Order.ItemAdded)
    def on_item_added(self, event: Order.ItemAdded) -> None:
        print(f"아이템 추가: {event.item_name}")
```

#### 비동기 핸들러

```python
@EventHandler()
class AsyncOrderEventHandler:
    @on_event(Order.Created)
    async def on_order_created(self, event: Order.Created) -> None:
        await send_notification(f"주문 {event.order_id} 접수됨")

    @on_event(Order.ItemAdded)
    async def on_item_added(self, event: Order.ItemAdded) -> None:
        await update_inventory(event.item_name)
```

#### 같은 이벤트, 여러 핸들러

하나의 Domain Event에 여러 핸들러를 등록할 수 있습니다. `@EventHandler` 자동 등록은 `AbstractDomainEvent` 서브클래스만 대상으로 하며, Integration Event는 bus/transport consumer 경로로 처리합니다.

```python
@EventHandler()
class NotificationHandler:
    @on_event(Order.Created)
    async def send_email(self, event: Order.Created) -> None:
        await email_service.send(f"주문 {event.order_id} 확인")

@EventHandler()
class AnalyticsHandler:
    @on_event(Order.Created)
    async def track_order(self, event: Order.Created) -> None:
        await analytics.track("order_created", event.total_amount)
```

### 트랜잭션과 연동해 발행

`@Transactional`과 함께 사용하면, 트랜잭션 커밋 후 이벤트가 자동 발행됩니다.

```python
from spakky.core.stereotype.usecase import UseCase
from spakky.data.aspects.transactional import transactional

@UseCase()
class CreateOrderUseCase:
    def __init__(self, order_repository: IOrderRepository) -> None:
        self._order_repository = order_repository

    @transactional
    async def execute(self, customer_name: str, total_amount: float) -> Order:
        # 1. Aggregate 생성 → 이벤트가 내부에 쌓임
        order = Order.create(
            customer_name=customer_name,
            total_amount=total_amount,
        )

        # 2. 아이템 추가 → 추가 이벤트
        order.add_item("노트북")
        order.add_item("마우스")

        # 3. Repository에 저장 → 내부에서 AggregateCollector.collect() 자동 호출
        return await self._order_repository.save(order)
        # 4. @Transactional 완료 시 → commit → 이벤트 자동 발행
```

### 타입별 발행 호출

```python
from spakky.event.publisher.domain_event_publisher import EventPublisher

# DomainEvent → Dispatcher → 인메모리 핸들러
domain_event = Order.Created(order_id=uuid4(), total_amount=1000)
publisher.publish(domain_event)  # EventMediator로 전달

# IntegrationEvent → Bus → 메시지 브로커
integration_event = OrderConfirmed(order_id="ORD-001", total_amount=5000)
publisher.publish(integration_event)  # RabbitMQ/Kafka로 전달
```

### 애플리케이션 설정

```python
import apps
import spakky.data
import spakky.event
import spakky.plugins.mediator
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(include={
        spakky.data.PLUGIN_NAME,
        spakky.event.PLUGIN_NAME,
        spakky.plugins.mediator.PLUGIN_NAME,
    })
    .scan(apps)             # @EventHandler 자동 검색
    .start()                # EventHandler ↔ 이벤트 타입 자동 매핑
)
```

!!! info "자동 등록"
    `app.start()` 시점에 `EventHandlerRegistrationPostProcessor`가 `@EventHandler` 클래스를 스캔하여 `@on_event` 메서드를 Domain Event 타입별로 자동 등록합니다. `AbstractIntegrationEvent`는 자동 등록 대상이 아니라 broker consumer 경로에서 처리됩니다.

---

## 다음 단계

- [이벤트 기반 아키텍처 통합 가이드](event-driven.md) — events·outbox·saga를 함께 쓰는 분산 워크플로우
- [이벤트 시스템 심화](../event-system.md) — 이벤트 정의, AggregateRoot 이벤트 수집, 인터페이스 구조
- [Transactional Outbox](outbox.md) — Integration Event의 원자적 기록과 성공 전달 경로의 at-least-once 의미

## 인프로세스 전용 구성과 후속 트랜잭션

Domain Event 처리에는 RabbitMQ/Kafka transport가 필요하지 않습니다. Integration Event를 외부로 발행할 때 transport를 설치하지 않았다면 `IntegrationEventTransportUnavailableError`로 거절합니다.

트랜잭션 이벤트 발행 Aspect의 Order는 0, TransactionalAspect의 Order는 1입니다. 이벤트 Aspect가 트랜잭션 실행을 감싸므로 commit 및 dispose 이후에만 성공 이벤트를 전달합니다. 수집 목록과 이벤트 배치를 분리한 뒤 핸들러를 호출하여 후속 유스케이스가 부모 이벤트를 재발행하지 않도록 합니다.

## 명시적인 이벤트 제공자 선택

`spakky-event`는 이벤트 계약·발행·Aspect와 제공자 검증을 소유합니다. 로컬 domain
consumer/dispatcher는 별도 `spakky-mediator` 플러그인을 설치하고 선택해야 합니다.
Kafka/RabbitMQ만 사용하는 서비스에는 로컬 mediator가 자동으로 등록되지 않습니다.
`spakky[event]`도 mediator를 숨겨 설치하지 않습니다.

| 구성 | 가능한 동작 |
| --- | --- |
| event | 계약과 발행 진입점; 없는 제공자로의 발행은 명시적 오류 |
| event + mediator | 동기·비동기 domain event 등록과 로컬 dispatch |
| event + Kafka | 동기·비동기 integration event 발행·소비 |
| event + mediator + Kafka | 두 이벤트 종류가 각 제공자로 독립적으로 전달됨 |

선언한 handler의 동기/비동기 및 domain/integration 역할에 맞는 consumer가 없으면
`EventHandlerProviderUnavailableError`로 기동을 실패시킵니다. domain 발행에 dispatcher가
없으면 `DomainEventDispatcherUnavailableError`, integration 발행에 transport가 없으면
`IntegrationEventTransportUnavailableError`를 발생시킵니다. 누락된 이벤트를 조용히 버리지 않습니다.

구현 import 이전과 설치 예시는 [Mediator API](../api/plugins/spakky-mediator.md)를 참고하세요.
