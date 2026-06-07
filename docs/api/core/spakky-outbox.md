# spakky-outbox

> `spakky-outbox`는 Integration Event를 transaction 바깥으로 안전하게 전달하기 위한 Outbox 계약을 제공합니다.

Outbox 패턴 — 이벤트 발행 보장

## 플러그인 진입점

::: spakky.outbox.main
options:
show_root_heading: false

## EventBus

::: spakky.outbox.bus.outbox_event_bus
options:
show_root_heading: false

## 포트

::: spakky.outbox.ports.storage
options:
show_root_heading: false

## Relay

::: spakky.outbox.relay
options:
show_root_heading: false

::: spakky.outbox.relay.relay
options:
show_root_heading: false

## 공통

::: spakky.outbox.common.config
options:
show_root_heading: false

::: spakky.outbox.common.message
options:
show_root_heading: false

## 에러

::: spakky.outbox.error
options:
show_root_heading: false

## 추가 모듈

::: spakky.outbox.relay.relay
    options:
      show_root_heading: false

::: spakky.outbox.main
    options:
      show_root_heading: false
