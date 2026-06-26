# spakky-agui

> `spakky-agui`는 `spakky-agent`의 protocol-neutral `AgentEvent` stream을 AG-UI 이벤트로 투영하고 FastAPI SSE, HTTP streaming, WebSocket, stdio 경계로 노출합니다.

AG-UI endpoint는 애플리케이션이 `RunDriverFactory`를 제공해 어떤 `@Agent`를 실행할지 결정합니다. plugin 초기화는 `AgUiConfig`만 등록하므로 endpoint wiring은 애플리케이션 코드에서 명시적으로 수행합니다.

## Public API

::: spakky.plugins.agui
    options:
      show_root_heading: false

## 설정

::: spakky.plugins.agui.config
    options:
      show_root_heading: false

## Endpoint

::: spakky.plugins.agui.endpoint
    options:
      show_root_heading: false

::: spakky.plugins.agui.http_stream
    options:
      show_root_heading: false

::: spakky.plugins.agui.websocket
    options:
      show_root_heading: false

::: spakky.plugins.agui.stdio
    options:
      show_root_heading: false

## Transport

::: spakky.plugins.agui.transport
    options:
      show_root_heading: false

## Projection

::: spakky.plugins.agui.projector
    options:
      show_root_heading: false

::: spakky.plugins.agui.hitl
    options:
      show_root_heading: false

::: spakky.plugins.agui.serialization
    options:
      show_root_heading: false

## Plugin

::: spakky.plugins.agui.main
    options:
      show_root_heading: false

## 에러

::: spakky.plugins.agui.error
    options:
      show_root_heading: false
