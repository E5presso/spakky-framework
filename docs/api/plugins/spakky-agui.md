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

## Multimodal inbound

Latest AG-UI user message의 content가 typed parts이면 nonblank text fragments를 newline으로
합쳐 `RunAgentInput.instruction`으로, image/audio/video/document parts를 ordered
`attachments` tuple로 매핑합니다. URL source는 `value`와 `mimeType`, data source는 strict
base64 `value`와 MIME type이 필요합니다. Deprecated binary, media-only message, missing MIME,
invalid URI/base64는 `AgUiRunResolutionError`입니다.

Default aggregate bound는 media 16개와 decoded inline bytes 20 MiB입니다. URL construction은
network I/O를 하지 않으며 provider-bound async DNS safety는 `spakky-llm` policy가 수행합니다.
Attachment provenance는 AG-UI message ID에 결속됩니다. Multimodal content를 사용해도 model
선택 shape는 계속 `forwardedProps.modelSelection.modelRef` 하나뿐입니다.

`RUN_PAUSED`를 deferred `hitl_approval` tool로 바꾸는 경로는 non-null
`approval_id`가 있는 approval-required pause만 지원합니다. Authentication/user-input
pause처럼 `approval_id=None`이면 `AgUiPendingApprovalError`이며 현재 별도 AG-UI pause
mapping은 없습니다. Event projection은 protocol-specific framing과 필드 선택을 수행하므로
무손실 또는 1:1 변환으로 간주하지 않습니다.

Iterative run에서는 model step마다 별도 message/reasoning ID를 사용합니다.
`STEP_FINISHED`를 투영하기 전에 열린 AG-UI text/reasoning/tool frame을 닫아 다음
`model-N` frame과 섞이지 않게 하며, 여러 model/tool step 뒤에도 terminal
`RUN_FINISHED`/`RUN_ERROR`는 한 번만 방출합니다.

Candidate-only model event에는 core runner가 missing tool START/END만 합성합니다. Signal
`Progress`는 `signal_progress` artifact를 거쳐 AG-UI `CUSTOM`이 되며 unsupported hook
yield는 `agent_signal_projection_unsupported` `RUN_ERROR`입니다. Canonical cancel도
`code="cancelled"` `RUN_ERROR` 하나이며 success terminal을 추가하지 않습니다.

Declared `output_type` final은 core가 만든 JSON-safe `output`을 AG-UI
`RUN_FINISHED.result`로 사용합니다. `output_type=None`이면 result는 `null`이며 기존
no-output Agent의 wire shape를 임의로 바꾸지 않습니다.
Structured-output terminal error는 result 대신 해당 `agent_structured_output_*` code의
`RUN_ERROR`입니다.

Protocol-native AG-UI `context` 배열은 현재 core `RunAgentInput.context`로 승격하지
않습니다. Exposed Agent의 typed dynamic context는 injected `IAgentContextProvider` 경로를
사용합니다.

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

::: spakky.plugins.agui.endpoint_input
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
