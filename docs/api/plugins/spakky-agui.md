# spakky-agui

> `spakky-agui`는 `spakky-agent`의 protocol-neutral `AgentEvent` stream을 AG-UI 이벤트로 투영하고 FastAPI SSE, HTTP streaming, WebSocket, stdio 경계로 노출합니다.

FastAPI SSE/HTTP streaming/WebSocket endpoint는 `@AgUiAgent @Agent` 선언을 `AgUiAgentRegistry`에 등록한 뒤 post-processor가 host FastAPI Pod에 자동 mount합니다. `add_agui_endpoint` 계열 helper는 lower-level 호환 API입니다.

## Public API

::: spakky.plugins.agui
    options:
      show_root_heading: false

## 설정

::: spakky.plugins.agui.config
    options:
      show_root_heading: false

## Endpoint

::: spakky.plugins.agui.stereotypes.agui_agent
    options:
      show_root_heading: false

::: spakky.plugins.agui.server.registry
    options:
      show_root_heading: false

::: spakky.plugins.agui.post_processors.mount_fastapi
    options:
      show_root_heading: false

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
