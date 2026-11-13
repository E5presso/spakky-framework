# ADR-0024: 구독자별 전달 계약과 멱등 소비

- **상태**: Accepted
- **날짜**: 2026-11-14

## 맥락 (Context)

통합 이벤트 소비자 인터페이스(`IIntegrationEventConsumer`)는 `register(event, handler)` 하나만 정의했다. 처리기를 어떻게 실행하고, 실패하면 무엇을 하는지는 인터페이스에 없었고, 그래서 구현체마다 동작이 달랐다.

- Kafka 플러그인은 애플리케이션에 consumer group 하나만 썼다. 같은 이벤트를 받는 처리기들은 순서대로 실행됐고, 하나가 실패하면 뒤 처리기는 실행되지 않았다. 재시도는 모든 처리기를 다시 실행했다. dead-letter 토픽은 토픽당 하나였다.
- RabbitMQ 플러그인은 이벤트 이름마다 큐 하나를 썼다. 재시도와 dead-letter가 없었고, 처리기 예외는 소비 콜백 밖으로 나갔다.
- 같은 이벤트를 서로 독립된 관심사가 받을 때, 한쪽의 실패나 지연이 다른 쪽을 막았다.
- 브로커는 적어도 한 번 전달하므로 같은 이벤트가 다시 올 수 있는데, 이미 처리한 이벤트를 건너뛰는 표준 방법이 없었다.
- 브로커 없이 통합 이벤트 흐름을 실행할 구현체가 없었다. mediator는 도메인 이벤트만 다룬다(ADR-0022).
- AOP가 적용된 처리기(예: `@Transactional`)는 프록시가 되어, 인스턴스에서 bound method를 찾는 등록 코드가 그 처리기를 조용히 빠뜨렸다.

## 결정 동인 (Decision Drivers)

- 모든 구현체는 인터페이스가 정한 스펙을 그대로 지켜야 한다. 구현체마다 달라지는 동작은 인터페이스에 정의가 빠졌다는 신호다.
- 재시도와 dead-letter는 토픽이 아니라 구독에 속한다. AWS SNS/SQS, Google Pub/Sub, Azure Service Bus, Spring Kafka가 모두 이 단위를 쓴다.
- 처리 기록은 처리기의 업무 변경과 같은 트랜잭션에 있어야 한다.
- 새 PyPI 패키지를 늘리지 않는다.

## 고려한 대안 (Considered Options)

### 대안 A: Kafka 플러그인에만 구독자별 consumer group을 추가

가장 작은 변경이다. 하지만 RabbitMQ와 메모리 구현체가 다시 다르게 동작하고, 멱등 키와 dead-letter 메타데이터의 형식이 구현체마다 갈린다.

### 대안 B: 전달 계약을 `spakky-event`에 두고 모든 구현체가 구현 (채택)

구독자, 처리기 실행, 재시도, dead-letter, 다시 넣기, 멱등 키를 `spakky-event`가 정의한다. 처리기 실행과 결과 판정은 공용 코드(`SubscriptionDelivery`)가 하고, 구현체는 판정 결과를 브로커 동작으로 옮긴다.

### 대안 C: 구독자 한 명에 이벤트 타입당 처리기 하나만 허용

부분 실패 문제가 구조적으로 사라지고 멱등 키가 단순해진다. 하지만 같은 관심사가 한 이벤트에 여러 반응을 다는 경우를 구독자 분리로만 풀게 되어, 소비 위치와 브로커 자원이 불필요하게 늘어난다.

### 멱등 소비를 켜는 방식

- 저장소 Pod가 있으면 자동 적용: 트랜잭션이 없는 처리기에서 기록과 업무 변경이 따로 커밋된다.
- 명시적 데코레이터(채택): 처리기가 `@Transactional()`과 함께 선언한다.

### 메모리 구현체의 위치

- mediator를 통합 이벤트까지 넓힘: 직렬화와 구독자 큐를 거치지 않아 브로커 동작과 달라진다.
- 새 플러그인 패키지: 경계는 분명하지만 PyPI 패키지가 늘어난다.
- `spakky-event` 안에 두되 자동 등록하지 않음(채택): ADR-0022의 "숨은 기본 소비자 없음"을 지킨다.

## 결정 (Decision)

대안 B를 채택한다.

1. **구독자**: `@EventHandler(subscriber="billing")`. 구독자마다 소비 위치, 재시도 상태, dead-letter 목적지가 따로다. 이름이 없으면 구현체의 기본 식별자를 쓰는 이름 없는 구독자다. 이름은 `[A-Za-z0-9][A-Za-z0-9_-]{0,62}`만 허용한다.
2. **처리기 실행**: 한 구독자 안에 같은 이벤트의 처리기를 여러 개 둘 수 있다. 한 처리기가 실패해도 나머지는 모두 실행한다. 실패가 남으면 전달을 재시도하고, 재시도는 아직 성공하지 못한 처리기만 실행한다.
3. **재시도**: `RetryPolicy`(총 시도 횟수, 첫 간격, 배수, 간격 상한, 모드)를 구독자마다 독립적으로 적용한다. 모드 `BLOCKING`은 순서를 지키고, `DELAYED`는 순서를 포기하고 뒤 메시지를 먼저 처리한다. `AbstractNonRetryableEventError`와 역직렬화 실패는 재시도하지 않는다. `EventDeferredError`는 시도 횟수를 세지 않고 기다린다.
4. **dead-letter**: 구독자마다 하나다. 메시지는 `DeadLetter` 메타데이터(원래 목적지, 구독자, 실패한 처리기별 예외 종류와 메시지, 시도 횟수, 시각)를 헤더로 가진다.
5. **다시 넣기**: `IEventRedriver.redrive(event, subscriber=..., limit=...)`는 실패한 구독자에게만, 실패한 처리기만 다시 실행한다.
6. **멱등 소비**: `@Idempotent()`가 `(구독자, 처리기, event_id)`를 `IProcessedEventStore`에 기록한다. aspect는 `@Transactional` 안쪽(order 2)에서 실행되어 기록이 처리기의 트랜잭션에 들어간다. 구현은 `spakky-sqlalchemy[event]`의 `spakky_event_inbox` 테이블이다.
7. **인증 기반 장애**: 인증 provider를 쓸 수 없는 오류는 메시지에 대한 판정이 아니므로 그대로 올리고, 구현체는 메시지를 확인(ack/commit)하지 않는다.
8. **처리기 등록**: 구현체는 `EventHandler.routes()`로 클래스에서 선언을 읽는다. 한 구독(구독자, 이벤트)에 동기·비동기 처리기를 섞으면 기동 시 `MixedSubscriptionModeError`가 난다. 두 소비자가 같은 브로커 구독을 나눠 읽어 메시지를 서로 놓치기 때문이다.
9. **메모리 구현체**: `spakky.event.memory.main.initialize(app)`로 명시적으로 켠다. 실제 직렬화를 거치고 같은 전달 계약을 따른다.

## 결과 (Consequences)

### 긍정적

- Kafka, RabbitMQ, 메모리 구현체가 실패 격리, 재시도, dead-letter, 다시 넣기에서 같은 동작을 한다.
- 한 구독자의 실패나 지연이 다른 구독자를 막지 않는다.
- 재시도와 다시 넣기가 이미 성공한 처리기를 다시 실행하지 않는다.
- AOP가 적용된 처리기가 등록에서 빠지지 않는다.

### 부정적

- Breaking change: `IIntegrationEventConsumer.register`의 시그니처가 넓어졌고, Kafka 설정 `max_handler_retries`가 `retry`로 바뀌었고, 동기·비동기 혼합 구독이 기동 오류가 됐다.
- 구독자마다 브로커 클라이언트와 자원(Kafka consumer group·토픽, RabbitMQ 큐)이 늘어난다.
- 순서 유지 재시도의 진행 상태는 프로세스 메모리에 있다. 프로세스가 죽으면 그 메시지는 첫 시도로 다시 전달되므로, 부작용이 있는 처리기는 `@Idempotent()`가 필요하다.

### 중립적

- 구독자별 재시도 정책 재정의는 두지 않았다. 정책은 구현체 설정 하나가 모든 구독자에 독립적으로 적용된다.
- 메모리 구현체는 전파된 인증 스냅샷을 검증하지 않으므로, 인가가 필요한 처리기는 기동 시 거부한다.
- 처리기 이름의 기본값은 `<클래스>.<메서드>`다. 이름을 바꾸면 멱등 키가 달라지므로 `@on_event(..., name=...)`로 고정할 수 있다.

## 참고 자료

- [ADR-0001 이벤트 시스템 재설계](0001-event-system-redesign.md)
- [ADR-0022 Optional domain event mediator provider](0022-optional-domain-event-mediator-provider.md)
- `core/spakky-event/src/spakky/event/delivery.py`, `idempotency.py`, `redrive.py`, `memory/`
