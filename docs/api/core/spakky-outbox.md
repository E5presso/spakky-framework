# spakky-outbox

> `spakky-outbox`는 Integration Event를 비즈니스 데이터와 같은 transaction에 원자적으로 기록하고 별도 Relay로 전송하기 위한 계약을 제공합니다. 브로커가 수락 가능한 레코드는 확인될 때까지 재전송되지만, 영구적인 레코드 귀속 거부는 retry 소진 후 성공 전달 없이 abandoned 처리될 수 있습니다.

Outbox 패턴 — 원자적 기록과 Relay 상태 계약

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
