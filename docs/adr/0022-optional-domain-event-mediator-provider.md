# ADR-0022: 로컬 Domain Event Mediator의 명시적 플러그인 분리

상태: Accepted · 2026-10-28 사용자 명시 결정

## 맥락

`spakky-event`가 기본 로컬 mediator와 handler 등록기를 제공하면서 Kafka도 같은
`IEventConsumer` 인터페이스를 구현해 두 플러그인의 후처리기에서 DI 후보가 충돌했다.
전역 바인딩으로 한쪽을 선택하면 다른 종류의 이벤트 handler를 잘못된 제공자로
등록할 수 있어, 단순한 Primary 선택으로 해결할 문제가 아니다.

## 결정

- event core는 계약·발행·Aspect·제공자 검증을 유지한다. 로컬 consumer를 기본 등록하지 않는다.
- `spakky-mediator`는 로컬 sync/async consumer·dispatcher와 domain handler 등록을 소유한다.
- core에 domain/integration 및 sync/async consumer 역할 계약을 둔다. 제공자가 없는
  handler 선언은 `EventHandlerProviderUnavailableError`로 기동을 실패시킨다.
- Kafka/RabbitMQ는 각자의 구체 consumer로 integration handler만 등록한다. 플러그인끼리 import하지 않는다.
- event-only 앱의 없는 dispatcher/transport를 필수 capability로 가장하지 않는다. 해당
  발행을 시도하면 typed configuration 오류가 발생한다.
- Kafka의 handler가 없는 consumer 모드는 빈 구독과 dead-letter producer 생성을 생략하며
  native lifecycle로 기동·종료한다. placeholder handler는 요구하지 않는다.

## 이전과 영향

`spakky.event.mediator`와 기존 core 등록기 import를 새 plugin 모듈로 옮기고 설치·선택을
명시한다. `event` extra가 mediator를 암묵적으로 포함하지 않는다. 공개 구체 import와
기본 등록 행위가 변경되므로 major release가 적합하다. ADR-0001의 이벤트 분류·발행
진입점은 유지하며, 기본 로컬 제공자 등록에 관한 부분은 이 결정으로 대체한다.

## 검증

event-only, event+mediator, event+Kafka, event+mediator+Kafka 조합을 검증한다.
제공자 누락, 로컬/외부 callback 분리, 실제 broker 왕복, sync/async 빈 소비자와 정상
종료를 각각 구분해서 확인한다.

## 기존 native 안정성 계약의 보존

기존 Amber가 직접 고정했던 공식 commit `94c88f98`·`1469b8fd`의 운영 계약을
새 제공자 구조에서도 유지한다. `EventDeferredError`는 실패 예산/DLT/commit 없이
유예하고 Kafka는 다른 partition과 heartbeat poll을 계속한다. 로컬 mediator는
이 특별한 예외를 삼키지 않고 호출자의 트랜잭션으로 전파한다.

여러 event loop가 한 async 엔진을 사용하는 앱은 공식 SQLAlchemy
`async_pool_mode=null`을 명시한다. NullPool 초기 연결·dialect 준비·정리는 native
lifecycle이 소유하며, 별도 sync driver URL과 TLS 신뢰 설정도 보존한다. 기본 queue
pool은 단일 event loop 앱에 남긴다. 이 선택의 연결 생성 비용과 실제 DB 부하는
별도 성능 검증 대상이다.
