# spakky-agui

> `spakky-agui`는 `spakky-agent`의 protocol-neutral `AgentEvent` stream을 AG-UI 이벤트로 투영하고 FastAPI SSE, HTTP streaming, WebSocket, stdio 경계로 노출합니다.

FastAPI SSE/HTTP streaming/WebSocket endpoint는 `@AGUICompatible @Agent` 선언을 `AgUiAgentRegistry`에 등록한 뒤 post-processor가 host FastAPI Pod에 자동 mount합니다. `add_agui_endpoint` 계열 helper는 lower-level 호환 API입니다.

## Model selection wire

AG-UI는 `forwardedProps.modelSelection`을 다음 exact shape로 core
`ModelSelection(model_ref=...)`에 매핑합니다.

```json
{
  "forwardedProps": {
    "modelSelection": {
      "modelRef": "support/primary"
    }
  }
}
```

`modelSelection` object는 `modelRef` 하나만 허용합니다. Blank/non-string ref와 legacy
provider/profile/raw model/selection metadata field는 `AgUiRunResolutionError`입니다.
Well-formed unknown ref는 shape parser exception이 아닙니다. Catalog-aware
`LlmAgentModel`이 `llm_model_selection_invalid` terminal model error를 내고 AG-UI
`RUN_ERROR`로 표면화합니다. Catalog 등록과 default 선택은
[LLM 모델 라우팅](../../guides/llm-routing.md)을 확인하세요.

`RUN_PAUSED`를 deferred `hitl_approval` tool로 바꾸는 경로는 non-null
`approval_id`가 있는 approval-required pause만 지원합니다. Authentication/user-input
pause처럼 `approval_id=None`이면 `AgUiPendingApprovalError`이며 현재 별도 AG-UI pause
mapping은 없습니다. Event projection은 protocol-specific framing과 필드 선택을 수행하므로
무손실 또는 1:1 변환으로 간주하지 않습니다.

## Public API

::: spakky.plugins.agui
    options:
      show_root_heading: false

## 설정

::: spakky.plugins.agui.config
    options:
      show_root_heading: false

## Endpoint

::: spakky.plugins.agui.stereotypes.agui_compatible
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
