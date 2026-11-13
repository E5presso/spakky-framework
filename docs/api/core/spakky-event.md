# spakky-event

> `spakky-event`는 이벤트 계약, 발행, provider 검증, handler stereotype을 제공하는 core 패키지입니다.

제공자 중립 이벤트 시스템 — EventBus, EventTransport 및 consumer/dispatcher 계약

## 플러그인 진입점

::: spakky.event.main
    options:
      show_root_heading: false

## Publisher 인터페이스

::: spakky.event.event_publisher
    options:
      show_root_heading: false

## Consumer 인터페이스

::: spakky.event.event_consumer
    options:
      show_root_heading: false

## Dispatcher 인터페이스

::: spakky.event.event_dispatcher
    options:
      show_root_heading: false

## EventBus

::: spakky.event.bus.transport_event_bus
    options:
      show_root_heading: false

## Auth Propagation

::: spakky.event.auth_propagation
    options:
      show_root_heading: false

## 로컬 제공자

로컬 구현은 별도 [spakky-mediator](../plugins/spakky-mediator.md) 플러그인이 소유합니다.

## Publisher

::: spakky.event.publisher.domain_event_publisher
    options:
      show_root_heading: false

## Aspect

::: spakky.event.aspects.transactional_event_publishing
    options:
      show_root_heading: false

## 전달 계약

통합 이벤트 소비자가 공통으로 따르는 구독자·재시도·dead-letter 계약입니다. 사용법은 [이벤트 시스템 가이드](../../guides/events.md#integration-event-전달-계약)를 참고하세요.

::: spakky.event.subscription
    options:
      show_root_heading: false

::: spakky.event.delivery
    options:
      show_root_heading: false

::: spakky.event.redrive
    options:
      show_root_heading: false

## 멱등 소비

::: spakky.event.idempotency
    options:
      show_root_heading: false

::: spakky.event.aspects.idempotent
    options:
      show_root_heading: false

## 메모리 구현체

자동으로 등록되지 않습니다. `spakky.event.memory.main.initialize(app)`로 켭니다.

::: spakky.event.memory.main
    options:
      show_root_heading: false

::: spakky.event.memory.broker
    options:
      show_root_heading: false

::: spakky.event.memory.consumer
    options:
      show_root_heading: false

::: spakky.event.memory.transport
    options:
      show_root_heading: false

::: spakky.event.memory.config
    options:
      show_root_heading: false

## 스테레오타입

::: spakky.event.stereotype.event_handler
    options:
      show_root_heading: false

## 후처리기

::: spakky.event.post_processor
    options:
      show_root_heading: false

## 에러

::: spakky.event.error
    options:
      show_root_heading: false
