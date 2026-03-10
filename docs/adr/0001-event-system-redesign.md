# ADR-0001: 이벤트 시스템 재설계 — 단일 진입점, EventBus/EventTransport 분리, Outbox Seam

- **상태**: Accepted
- **날짜**: 2026-03-06

## 맥락 (Context)

현재 `spakky-event`는 세 가지 구조적 문제를 가지고 있다:

1. **EventDispatcher 구현 불일치**: `DomainEventMediator`는 존재하지만, `IntegrationEventMediator`는 core에 구현체가 없다. Integration 쪽 Dispatcher/Consumer 인터페이스는 선언만 존재.
2. **Domain/Integration 파이프라인 2벌 중복**: Publisher 4개, Dispatcher 4개, Consumer 4개 = 12개 인터페이스가 Domain/Integration × Sync/Async로 분리되어 있다. 내부적으로 타입 기반 라우팅으로 통합할 수 있는 부분이 과도하게 분리됨.
3. **Outbox 삽입 seam 부재**: Kafka/RabbitMQ 플러그인이 `IIntegrationEventPublisher`를 직접 구현하므로, 중간에 Outbox publisher를 끼워넣을 구조적 여지가 없다.

## 결정 동인 (Decision Drivers)

- **단순성**: 인터페이스와 Concept Count 최소화
- **확장성**: Outbox, 새 transport 추가 시 core 변경 없이 가능해야 함
- **단방향 의존**: `spakky-sqlalchemy`가 `spakky-event`에 의존하면 안 됨
- **Opt-in 원칙**: Outbox는 원하는 사용자만 활성화
- **Fail Loudly**: Transport 미설치 시 silent fallback 금지, 즉시 에러
- **Spring Boot 및 eShopOnContainers의 검증된 패턴**: 두 프레임워크 모두 동일한 구조적 해법을 사용

## 선행 조사 (Prior Art)

### Spring Boot / Spring Modulith

- `ApplicationEventPublisher` — **단일 이벤트 발행 진입점**
- `@EventListener` — 인프로세스 핸들러 바인딩
- `@TransactionalEventListener(phase = AFTER_COMMIT)` — 트랜잭션 인지 핸들러
- Spring Modulith — **opt-in 이벤트 외부화** (outbox 자동 지원)
- 핵심: Domain Event는 항상 인프로세스, 외부화는 별도 선택적 레이어

### ASP.NET Core / eShopOnContainers

- `MediatR.IMediator.Publish()` — **인프로세스 미디에이터** (Domain Event 전용)
- `INotificationHandler<T>` — 핸들러 패턴
- `IntegrationEventLogService` — **전용 outbox** (Integration Event만)
- `IEventBus` — **전송 추상화** (RabbitMQ, Azure Service Bus 구현)
- 흐름: Aggregate → DomainEvent → MediatR 인프로세스 → 핸들러가 IntegrationEvent 생성 → Outbox 저장 (같은 트랜잭션) → 커밋 후 Bus로 발행
- 핵심: Domain/Integration 완전 분리, Outbox는 인프라 레이어에 위치, opt-in

### 두 프레임워크의 공통 패턴

| 패턴                    | Spring                          | eShop                                 | spakky 적용                  |
| ----------------------- | ------------------------------- | ------------------------------------- | ---------------------------- |
| 단일 진입점             | `ApplicationEventPublisher`     | `IMediator.Publish()`                 | `IEventPublisher`            |
| Domain = In-Process     | `@EventListener`                | MediatR → `INotificationHandler`      | `EventMediator`              |
| Integration = 외부 전송 | Spring Modulith externalization | `IEventBus` + outbox                  | `IEventBus` → `IEventTransport` |
| Outbox = Opt-in         | Spring Modulith (선택적)        | `IntegrationEventLogService` (선택적) | `OutboxEventBus` (`@Primary` PnP)  |
| 핸들러가 결정           | `@EventListener` 내 외부 발행   | Handler → IntegrationEvent 생성       | `@on_event` 핸들러 내 결정   |
| Outbox ≠ Core           | 인프라 레이어                   | 인프라 레이어                         | 퍼시스턴스 플러그인          |

### Outbox PnP 구현 사례 조사

Outbox를 PnP(Plug and Play) 플러그인으로 자연스럽게 끼울 수 있는 설계가 현실적인지 확인하기 위해, 주요 프레임워크의 구현 메커니즘을 조사했다.

| 프레임워크        | PnP? | 메커니즘                                  | DI Decorator? |
| ----------------- | ---- | ----------------------------------------- | ------------- |
| Spring Modulith   | O    | `BeanPostProcessor` (bean 교체)           | X             |
| MassTransit       | O    | 미들웨어 파이프라인 (behavior filter)     | X             |
| NServiceBus       | O    | 파이프라인 behavior                       | X             |
| CAP (DotNetCore)  | O    | 내장 설계 (publish → DB → relay)          | X             |

**공통 결론**: PnP outbox 자체는 실현 가능하다. 그러나 **어떤 프레임워크도 순수 DI Decorator 체이닝으로 PnP outbox를 구현하지 않는다.** Spring은 BeanPostProcessor(bean 교체), MassTransit/NServiceBus는 메시지 파이프라인, CAP은 처음부터 outbox를 프레임워크 내장으로 설계했다.

### Spakky DI 컨테이너의 Decorator 한계

Spakky의 `ApplicationContext`는 같은 인터페이스의 복수 구현체가 존재할 때 `@Primary` → `Qualifier` → `name` 순으로 하나를 선택한다. 그러나 **Decorator 자동 체이닝은 지원하지 않는다.**

`OutboxEventBus(IEventBus)`가 `IEventBus`의 Decorator로서 내부에 `_inner: IEventBus`를 주입받으려 하면:
- `@Primary`가 `OutboxEventBus`에 있으면 → 자기 자신이 `_inner`에 주입되어 **무한 재귀**
- `@Primary`가 없으면 → 두 구현체가 경쟁하여 **`NoUniquePodError`**

이 한계가 대안 D를 도출한 핵심 근거다.

## 고려한 대안 (Considered Options)

### 대안 A: 현상 유지 + Integration Mediator 추가

Domain과 동일하게 `IntegrationEventMediator`를 core에 추가하고, 12개 인터페이스 체계를 유지.

- **장점**: Breaking change 없음
- **단점**: 근본 문제(중복, outbox seam 부재) 해결 안 됨. Concept Count 증가.

### 대안 B: CompositeEventPublisher (초기 제안)

`CompositeEventPublisher`가 여러 "Gateway"를 조합하여 이벤트를 분배.

- **장점**: 유연한 구성
- **단점**: Gateway 선택 로직 불명확, "Sinker" 등 네이밍 논란, DX 복잡, 모든 Gateway가 모든 이벤트 타입을 알아야 함.

### 대안 C: 타입 기반 라우터 + EventBus 분리

단일 `IEventPublisher`가 `AbstractEvent` 타입으로 라우팅:

- `AbstractDomainEvent` → `EventMediator` (in-process)
- `AbstractIntegrationEvent` → `IEventBus` (외부 전송)

`IEventBus`는 Decorator 패턴으로 Outbox를 삽입할 수 있는 seam 제공.

- **장점**: Spring/eShop 검증 패턴과 일치, 인터페이스 수 절감, 명확한 라우팅
- **단점**: Breaking change. **Outbox를 `IEventBus` Decorator로 구현 시 Spakky DI 컨테이너의 자기참조 문제 발생** (위 "Spakky DI 컨테이너의 Decorator 한계" 참조). Outbox가 Kafka/RabbitMQ와 동일 인터페이스를 놓고 DI 경쟁.

### 대안 D: 타입 기반 라우터 + EventBus/EventTransport 2단 분리 (채택)

대안 C의 타입 기반 라우팅을 유지하되, Integration Event 경로를 2단 인터페이스로 분리:

- `IEventBus` — Integration Event 발행 진입점 (EventPublisher가 의존)
- `IEventTransport` — 실제 메시지 전송 (Kafka/RabbitMQ가 구현)

기본 구현 `TransportEventBus(IEventBus)`는 `IEventTransport`에 직접 위임한다. Outbox 플러그인은 `IEventBus`를 `@Primary`로 교체하여 seam을 차지한다. 두 인터페이스가 다르므로 **DI 경쟁이 구조적으로 발생하지 않는다.**

- **장점**: 대안 C의 장점 + DI 경쟁 완전 제거, `@Primary`만으로 Outbox PnP 달성, `OutboxRelay`는 `IEventTransport`에 의존하므로 자기참조 없음
- **단점**: Breaking change. `TransportEventBus`가 순수 pass-through 위임 클래스 (Concept Count +1)

## 결정 (Decision)

**대안 D를 채택한다.**

대안 C의 타입 기반 라우팅을 유지하되, Integration Event 경로를 `IEventBus`(진입점) / `IEventTransport`(전송)로 2단 분리한다.

### 인터페이스 변경

#### 신규

| 인터페이스                                               | 역할                                                      |
| -------------------------------------------- | --------------------------------------------------------- |
| `IEventPublisher` / `IAsyncEventPublisher`   | 단일 발행 진입점. `AbstractEvent`를 받아 타입 기반 라우팅 |
| `IEventBus` / `IAsyncEventBus`               | Integration Event 발행 진입점. Outbox seam 역할            |
| `IEventTransport` / `IAsyncEventTransport`   | 실제 메시지 전송 추상화. Kafka/RabbitMQ가 구현       |
| `IEventDispatcher` / `IAsyncEventDispatcher` | 통합 인프로세스 dispatch (기존 Domain 전용에서 확장)      |
| `IEventConsumer` / `IAsyncEventConsumer`     | 통합 핸들러 등록 (기존 Domain 전용에서 확장)              |

#### 삭제

| 인터페이스                                                         | 대체                              |
| ------------------------------------------------------------------ | --------------------------------- |
| `IDomainEventPublisher` / `IAsyncDomainEventPublisher`             | `IEventPublisher`                 |
| `IIntegrationEventPublisher` / `IAsyncIntegrationEventPublisher`   | `IEventBus`                       |
| `IDomainEventDispatcher` / `IAsyncDomainEventDispatcher`           | `IEventDispatcher`                |
| `IIntegrationEventDispatcher` / `IAsyncIntegrationEventDispatcher` | 삭제 (선언만 존재, 구현체 없음) |
| `IDomainEventConsumer` / `IAsyncDomainEventConsumer`               | `IEventConsumer`                  |
| `IIntegrationEventConsumer` / `IAsyncIntegrationEventConsumer`     | Transport PostProcessor 직접 관리 |

#### 구현체 변경

| Before                   | After                                                          |
| ------------------------ | -------------------------------------------------------------- |
| `DomainEventMediator`    | `EventMediator` (AbstractEvent 전체 다룸)                    |
| `DomainEventPublisher`   | `EventPublisher` (타입 기반 라우터)                          |
| (신규)                    | `TransportEventBus` (implements `IEventBus`, `IEventTransport`에 위임) |
| `KafkaEventPublisher`    | `KafkaEventTransport` (implements `IAsyncEventTransport`)      |
| `RabbitMQEventPublisher` | `RabbitMQEventTransport` (implements `IAsyncEventTransport`)   |

### EventPublisher 라우팅 로직

```python
@Pod()
class AsyncEventPublisher(IAsyncEventPublisher):
    _mediator: IAsyncEventDispatcher
    _bus: IAsyncEventBus | None  # None if no transport plugin installed

    async def publish(self, event: AbstractEvent) -> None:
        match event:
            case AbstractDomainEvent():
                await self._mediator.dispatch(event)
            case AbstractIntegrationEvent():
                if self._bus is None:
                    raise EventBusNotConfiguredError(...)
                await self._bus.send(event)
            case _:
                raise AssertionError(f"Unknown event type: {type(event)!r}")
```

### TransportEventBus (기본 구현)

```python
@Pod()
class AsyncTransportEventBus(IAsyncEventBus):
    """IEventTransport에 직접 위임하는 기본 EventBus."""
    _transport: IAsyncEventTransport

    async def send(self, event: AbstractIntegrationEvent) -> None:
        await self._transport.send(event)
```

Outbox 플러그인이 없으면 `AsyncTransportEventBus`가 유일한 `IAsyncEventBus` 구현체로 주입된다.
Outbox 플러그인이 있으면 `OutboxEventBus`가 `@Primary`로 `IAsyncEventBus`를 교체한다.

### End-to-End 흐름

#### Domain Event만 (가장 단순)

```
UseCase(@Transactional)
  → repository.save(order) → collector.collect(order)
  → [Aspect after_returning] → publisher.publish(OrderCreatedEvent)
    → mediator.dispatch() → OrderCreatedHandler.handle()
  → COMMIT
```

#### Domain → Integration (외부 전송)

```
  → publisher.publish(OrderCreatedEvent)
    → mediator.dispatch()
      → OrderCreatedHandler.handle()
        → publisher.publish(OrderCreatedIntegrationEvent)  ← 핸들러가 결정
          → bus.send() → TransportEventBus → KafkaEventTransport → Kafka
```

#### Outbox 적용 (PnP 플러그인)

```
  → bus.send(OrderCreatedIntegrationEvent)
    → OutboxEventBus.send()  ← @Primary로 TransportEventBus 교체
      → outbox_table.insert() (같은 트랜잭션)
  → COMMIT

  [OutboxRelay - background]
    → outbox_table poll → KafkaEventTransport.send() → 발행 완료 마킹
```

`OutboxRelay`는 `IEventTransport`에 의존하므로 `IEventBus`와 DI 경쟁이 없다.

### 패키지 경계

```
spakky-domain       AbstractEvent, AbstractDomainEvent, AbstractIntegrationEvent
      ↓
spakky-data         AggregateCollector, @Transactional
      ↓
spakky-event        IEventPublisher, IEventBus, IEventTransport,
                    EventMediator, EventPublisher, TransportEventBus,
                    TransactionalEventPublishingAspect
      ↓         ↓
spakky-kafka    spakky-rabbitmq
(KafkaEventTransport) (RabbitMQEventTransport)
```

- `spakky-sqlalchemy`는 `spakky-data`만 의존. `spakky-event`에 의존하지 않음.
- Outbox 구현은 별도 opt-in 패키지 (아래 "Outbox 위치" 참조).

### Outbox 위치

**별도 패키지 `spakky-outbox-sqlalchemy`를 권장한다.**

| 선택지                                             | 설명                                                                    | 판정         |
| -------------------------------------------------- | ----------------------------------------------------------------------- | ------------ |
| A. `spakky-sqlalchemy` 내 optional 모듈            | `spakky.plugins.sqlalchemy.event.outbox`, `spakky-event`를 optional dep | 의존 방향 역전 |
| **B. 별도 패키지 `spakky-outbox-sqlalchemy`**   | `spakky-event` + `spakky-sqlalchemy` 의존                               | **채택**      |
| C. `spakky-event`에 outbox 추상화, 구현은 플러그인 | interface만 core, impl은 persistence 플러그인                           | 과도 설계    |

별도 패키지 방식의 장점:
- `spakky-sqlalchemy`가 `spakky-event`에 의존하지 않음 (단방향 의존 유지)
- `spakky-outbox-sqlalchemy`는 두 패키지에 의존하는 교차점 패키지
- 설치 여부로 PnP 달성: `uv add spakky-outbox-sqlalchemy` 한 줄로 활성화

## 마이그레이션 계획

### Phase 1: 인터페이스 통합 (Breaking Change)

1. `IEventPublisher` / `IAsyncEventPublisher` 정의
2. `IEventBus` / `IAsyncEventBus` 정의
3. `IEventTransport` / `IAsyncEventTransport` 정의
4. `EventMediator` / `AsyncEventMediator` 구현 (DomainEventMediator 리네임 + 제네릭화)
5. `EventPublisher` / `AsyncEventPublisher` 구현 (타입 기반 라우터)
6. `TransportEventBus` / `AsyncTransportEventBus` 구현 (기본 Bus → Transport 위임)
7. `TransactionalEventPublishingAspect`에서 `IAsyncEventPublisher`로 교체
8. `EventHandlerRegistrationPostProcessor` 업데이트
9. 구 인터페이스 삭제
10. `main.py` `initialize()` 업데이트

### Phase 2: Transport 플러그인 마이그레이션

1. `KafkaEventPublisher` → `KafkaEventTransport` (implements `IAsyncEventTransport`)
2. `RabbitMQEventPublisher` → `RabbitMQEventTransport` (implements `IAsyncEventTransport`)
3. Kafka/RabbitMQ PostProcessor 업데이트
4. 플러그인 `main.py` `initialize()` 업데이트

### Phase 3: Outbox 확장 (Non-breaking, PnP)

1. `spakky-outbox-sqlalchemy` 패키지 생성
2. `OutboxEventBus(IAsyncEventBus)` 구현 — `@Primary`로 `TransportEventBus` 교체
3. `IOutboxRepository` 인터페이스 + SQLAlchemy 구현체
4. `OutboxRelay(IAsyncBackgroundService)` — `IAsyncEventTransport` 의존으로 실제 전송
5. Outbox 테이블 마이그레이션 (Alembic)

## 결과 (Consequences)

### 긍정적

- **인터페이스 수 절감**: 12개 → 10개 (6개 통합 + 2개 Bus + 2개 Transport)
- **Outbox seam 확보**: `IEventBus`/`IEventTransport` 2단 분리로 DI 경쟁 없이 Outbox PnP 가능
- **검증된 패턴**: Spring Boot, eShopOnContainers와 구조적으로 일치
- **명확한 라우팅**: 타입 기반 dispatch로 Domain/Integration 경로 명확
- **Fail Loudly**: Transport 미설치 시 `EventBusNotConfiguredError`

### 부정적

- **Breaking Change**: 기존 인터페이스를 사용하는 모든 코드 수정 필요
- **Phase 1 작업량**: core + 2개 plugin 동시 마이그레이션
- **Concept Count +1**: `TransportEventBus`가 순수 pass-through 위임 클래스로 존재

### 중립적

- **`IEventBus` optional 주입**: DI 컨테이너에서 `None` 기본값 해석이 필요할 수 있음

## 참고 자료

- [Spring Framework — ApplicationEventPublisher](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events)
- [Spring Modulith — Event Externalization](https://docs.spring.io/spring-modulith/reference/events.html)
- [eShopOnContainers — Domain Events](https://learn.microsoft.com/en-us/dotnet/architecture/microservices/microservice-ddd-cqrs-patterns/domain-events-design-implementation)
- [eShopOnContainers — Integration Events](https://learn.microsoft.com/en-us/dotnet/architecture/microservices/multi-container-microservice-net-applications/integration-event-based-microservice-communications)
- [MassTransit — Transactional Outbox](https://masstransit.io/documentation/patterns/transactional-outbox)
- [Martin Fowler — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
