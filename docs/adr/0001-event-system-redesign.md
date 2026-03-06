# ADR-0001: 이벤트 시스템 재설계 — 단일 진입점, EventBus, Outbox Seam

- **상태**: Proposed
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
| Integration = 외부 전송 | Spring Modulith externalization | `IEventBus` + outbox                  | `IEventBus`                  |
| Outbox = Opt-in         | Spring Modulith (선택적)        | `IntegrationEventLogService` (선택적) | `OutboxEventBus` (Decorator) |
| 핸들러가 결정           | `@EventListener` 내 외부 발행   | Handler → IntegrationEvent 생성       | `@on_event` 핸들러 내 결정   |
| Outbox ≠ Core           | 인프라 레이어                   | 인프라 레이어                         | 퍼시스턴스 플러그인          |

## 고려한 대안 (Considered Options)

### 대안 A: 현상 유지 + Integration Mediator 추가

Domain과 동일하게 `IntegrationEventMediator`를 core에 추가하고, 12개 인터페이스 체계를 유지.

- **장점**: Breaking change 없음
- **단점**: 근본 문제(중복, outbox seam 부재) 해결 안 됨. Concept Count 증가.

### 대안 B: CompositeEventPublisher (초기 제안)

`CompositeEventPublisher`가 여러 "Gateway"를 조합하여 이벤트를 분배.

- **장점**: 유연한 구성
- **단점**: Gateway 선택 로직 불명확, "Sinker" 등 네이밍 논란, DX 복잡, 모든 Gateway가 모든 이벤트 타입을 알아야 함.

### 대안 C: 타입 기반 라우터 + EventBus 분리 (채택)

단일 `IEventPublisher`가 `AbstractEvent` 타입으로 라우팅:

- `AbstractDomainEvent` → `EventMediator` (in-process)
- `AbstractIntegrationEvent` → `IEventBus` (외부 전송)

`IEventBus`는 Decorator 패턴으로 Outbox를 삽입할 수 있는 seam 제공.

- **장점**: Spring/eShop 검증 패턴과 일치, 인터페이스 수 절감, Outbox seam 확보, 명확한 라우팅
- **단점**: Breaking change (기존 인터페이스 삭제/리네임 필요)

## 결정 (Decision)

**대안 C를 채택한다.**

### 인터페이스 변경

#### 신규

| 인터페이스                                   | 역할                                                      |
| -------------------------------------------- | --------------------------------------------------------- |
| `IEventPublisher` / `IAsyncEventPublisher`   | 단일 발행 진입점. `AbstractEvent`를 받아 타입 기반 라우팅 |
| `IEventBus` / `IAsyncEventBus`               | Integration Event 전송 추상화. Kafka/RabbitMQ가 구현      |
| `IEventDispatcher` / `IAsyncEventDispatcher` | 통합 인프로세스 dispatch (기존 Domain 전용에서 확장)      |
| `IEventConsumer` / `IAsyncEventConsumer`     | 통합 핸들러 등록 (기존 Domain 전용에서 확장)              |

#### 삭제

| 인터페이스                                                         | 대체                              |
| ------------------------------------------------------------------ | --------------------------------- |
| `IDomainEventPublisher` / `IAsyncDomainEventPublisher`             | `IEventPublisher`                 |
| `IIntegrationEventPublisher` / `IAsyncIntegrationEventPublisher`   | `IEventBus`                       |
| `IDomainEventDispatcher` / `IAsyncDomainEventDispatcher`           | `IEventDispatcher`                |
| `IIntegrationEventDispatcher` / `IAsyncIntegrationEventDispatcher` | 삭제 (core 구현체 없었음)         |
| `IDomainEventConsumer` / `IAsyncDomainEventConsumer`               | `IEventConsumer`                  |
| `IIntegrationEventConsumer` / `IAsyncIntegrationEventConsumer`     | Transport PostProcessor 직접 관리 |

#### 구현체 변경

| Before                   | After                                            |
| ------------------------ | ------------------------------------------------ |
| `DomainEventMediator`    | `EventMediator` (AbstractEvent 전체 다룸)        |
| `DomainEventPublisher`   | `EventPublisher` (타입 기반 라우터)              |
| `KafkaEventPublisher`    | `KafkaEventBus` (implements `IAsyncEventBus`)    |
| `RabbitMQEventPublisher` | `RabbitMQEventBus` (implements `IAsyncEventBus`) |

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
          → bus.send() → KafkaEventBus
```

#### Outbox 적용 (미래)

```
  → bus.send(OrderCreatedIntegrationEvent)
    → OutboxEventBus.send()  ← Decorator
      → outbox_table.insert() (같은 트랜잭션)
  → COMMIT

  [OutboxRelay - background]
    → outbox_table poll → KafkaEventBus.send() → 발행 완료 마킹
```

### 패키지 경계

```
spakky-domain       AbstractEvent, AbstractDomainEvent, AbstractIntegrationEvent
      ↓
spakky-data         AggregateCollector, @Transactional
      ↓
spakky-event        IEventPublisher, IEventBus, EventMediator, EventPublisher,
                    TransactionalEventPublishingAspect
      ↓         ↓
spakky-kafka    spakky-rabbitmq
(KafkaEventBus) (RabbitMQEventBus)
```

- `spakky-sqlalchemy`는 `spakky-data`만 의존. `spakky-event`에 의존하지 않음.
- Outbox 구현은 별도 opt-in 모듈 (아래 "Outbox 위치" 참조).

### Outbox 위치 (미결정 — Phase 3에서 결정)

| 선택지                                             | 설명                                                                    |
| -------------------------------------------------- | ----------------------------------------------------------------------- |
| A. `spakky-sqlalchemy` 내 optional 모듈            | `spakky.plugins.sqlalchemy.event.outbox`, `spakky-event`를 optional dep |
| B. 별도 패키지 `spakky-outbox-sqlalchemy`          | `spakky-event` + `spakky-sqlalchemy` 의존                               |
| C. `spakky-event`에 outbox 추상화, 구현은 플러그인 | interface만 core, impl은 persistence 플러그인                           |

## 마이그레이션 계획

### Phase 1: 인터페이스 통합 (Breaking Change)

1. `IEventPublisher` / `IAsyncEventPublisher` 정의
2. `IEventBus` / `IAsyncEventBus` 정의
3. `EventMediator` / `AsyncEventMediator` 구현 (DomainEventMediator 리네임 + 제네릭화)
4. `EventPublisher` / `AsyncEventPublisher` 구현 (타입 기반 라우터)
5. `TransactionalEventPublishingAspect`에서 `IAsyncEventPublisher`로 교체
6. `EventHandlerRegistrationPostProcessor` 업데이트
7. 구 인터페이스 삭제
8. `main.py` `initialize()` 업데이트

### Phase 2: Transport 플러그인 마이그레이션

1. `KafkaEventPublisher` → `KafkaEventBus` (implements `IAsyncEventBus`)
2. `RabbitMQEventPublisher` → `RabbitMQEventBus` (implements `IAsyncEventBus`)
3. Kafka/RabbitMQ PostProcessor 업데이트
4. 플러그인 `main.py` `initialize()` 업데이트

### Phase 3: Outbox 확장 (미래, Non-breaking)

1. `OutboxEventBus(IAsyncEventBus)` Decorator 구현
2. `OutboxRelay` 백그라운드 릴레이 구현
3. Persistence 플러그인별 outbox storage 구현

## 결과 (Consequences)

### 긍정적

- **인터페이스 수 절감**: 12개 → 8개 (6개 통합 + 2개 신규 Bus)
- **Outbox seam 확보**: `IEventBus` Decorator로 Outbox 삽입 가능
- **검증된 패턴**: Spring Boot, eShopOnContainers와 구조적으로 일치
- **명확한 라우팅**: 타입 기반 dispatch로 Domain/Integration 경로 명확
- **Fail Loudly**: Transport 미설치 시 `EventBusNotConfiguredError`

### 부정적

- **Breaking Change**: 기존 인터페이스를 사용하는 모든 코드 수정 필요
- **Phase 1 작업량**: core + 2개 plugin 동시 마이그레이션

### 중립적

- **`IEventBus` optional 주입**: DI 컨테이너에서 `None` 기본값 해석이 필요할 수 있음
- **Outbox 위치**: Phase 3에서 구체화 필요

## 참고 자료

- [Spring Framework — ApplicationEventPublisher](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events)
- [Spring Modulith — Event Externalization](https://docs.spring.io/spring-modulith/reference/events.html)
- [eShopOnContainers — Domain Events](https://learn.microsoft.com/en-us/dotnet/architecture/microservices/microservice-ddd-cqrs-patterns/domain-events-design-implementation)
- [eShopOnContainers — Integration Events](https://learn.microsoft.com/en-us/dotnet/architecture/microservices/multi-container-microservice-net-applications/integration-event-based-microservice-communications)
- [Martin Fowler — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
