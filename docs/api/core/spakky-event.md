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
