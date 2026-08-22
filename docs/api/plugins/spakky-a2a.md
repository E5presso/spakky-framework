# spakky-a2a

> `spakky-a2a`는 `@Agent`를 A2A AgentCard와 task transport로 노출하고, 원격 A2A teammate를 `spakky-agent` delegation stream으로 합류시키는 어댑터입니다.

서버 경로는 공식 `a2a-sdk` request handler와 task store를 사용하며, 실행은 `IAgentRunnerFactory`가 여는 runner의 `AgentEvent` stream을 A2A task/message/artifact update로 투영합니다. `@A2ACompatible @Agent`는 registry에 등록되고 ASGI host Pod가 있으면 JSON-RPC/REST endpoint가 자동 mount됩니다. `spakky-grpc`의 `GrpcServerSpec`가 있으면 gRPC handler도 선언형으로 등록됩니다.

## Model selection data part

A2A message data part는 canonical `modelSelection` container만 허용하며, 내부 object는
camelCase `modelRef` 하나만 가집니다.

```json
{
  "modelSelection": {
    "modelRef": "support/primary"
  }
}
```

Legacy `model_selection`, 한 message의 여러 data part에 중복된 selector,
blank/non-string ref, `model_ref`, legacy provider/profile/raw model/selection metadata
field는 `A2ARunResolutionError`입니다. Well-formed unknown ref는 shape parser exception이
아니며 `LlmAgentModel`의 `llm_model_selection_invalid` terminal error가 A2A failed task로
표면화됩니다. Catalog 등록과 default 선택은
[LLM 모델 라우팅](../../guides/llm-routing.md)을 확인하세요.

## Multimodal inbound

A2A executor는 inbound message의 text를 `RunAgentInput.instruction`으로 사용하고 raw/URL
parts를 MIME family에 따라 `ImagePart`, `AudioPart`, `VideoPart`, `DocumentPart` attachment로
매핑합니다. Raw bytes와 URL은 provider I/O 전에 core safety contract를 통과하고 document
filename은 있을 때 보존됩니다. Data parts는 attachment로 해석하지 않습니다.

일반 run은 nonblank text가 필요하고 approval-only resume만 `"resume"` marker를 사용합니다.
Default aggregate bound는 media 16개와 inline bytes 20 MiB입니다. Unknown content kind,
empty bytes, missing/unsupported MIME, local URI와 bound 초과는 `A2ARunResolutionError`입니다.
Attachment provenance는 A2A message ID에 결속되며 model selection은 별도 data part의
`modelSelection.modelRef` exact shape를 유지합니다.

Inbound `metadata`는 얕게 합쳐지고 top-level `mcp`는 같은 metadata key를 씁니다. 같은
data part에서는 top-level `mcp`가 `metadata.mcp`를 덮어쓰고 여러 part에서는 뒤 값이
앞 값을 덮어쓰므로 두 입력 경로를 혼용하지 않습니다. Remote delegation은 text와
working/completed/failed 상태 중심의 축약 mapping이며 모든 remote part/state를 1:1로
보존하지 않습니다.

Local iterative run의 `model-N`/`tool-N` step은 ordered working status와 result artifact로
이어집니다. Model step의 provider `DONE`은 task terminal이 아니며, executor가 전체
runner stream을 drain한 뒤 A2A complete/failed를 한 번만 reconcile합니다.

Candidate-only tool call은 core가 missing START/END만 합성해 working metadata로 투영합니다.
Signal `Progress`는 `signal_progress` artifact가 되고 unsupported signal yield는
`agent_signal_projection_unsupported` failed task입니다. In-run canonical cancel도
`cancelled` failed task이며 별도 A2A cancel operation의 canceled state와는 다른 경로입니다.

Structured final은 JSON-safe `output` data part와 declared type 이름의 artifact로 투영한 뒤
task를 complete합니다. `output_type=None`이면 이 final artifact를 추가하지 않습니다.
Structured-output terminal error는 artifact 없이 error data를 가진 failed task입니다.

A2A data part는 현재 core `AgentContext` inbound가 아닙니다. Typed dynamic context는 exposed
Agent constructor의 `IAgentContextProvider`로 공급합니다.

Approval resume data part는 현재 `approval_id`와 `decision`만 core signal로 옮깁니다.
`modified_payload`는 전달하지 않으므로 argument-bearing `MODIFY`는 A2A ingress에서
지원하지 않습니다. Core runner의 MODIFY 기능이 A2A wire에서도 자동 제공된다고 가정하면
안 됩니다.

## Public API

::: spakky.plugins.a2a
    options:
      show_root_heading: false

## 설정

::: spakky.plugins.a2a.config
    options:
      show_root_heading: false

## AgentCard

::: spakky.plugins.a2a.card.derivation
    options:
      show_root_heading: false

## 서버 등록

::: spakky.plugins.a2a.stereotypes.a2a_compatible
    options:
      show_root_heading: false

::: spakky.plugins.a2a.server.registry
    options:
      show_root_heading: false

::: spakky.plugins.a2a.server.builder
    options:
      show_root_heading: false

::: spakky.plugins.a2a.server.request_handler
    options:
      show_root_heading: false

## Executor

::: spakky.plugins.a2a.executor.adapter
    options:
      show_root_heading: false

::: spakky.plugins.a2a.executor.event_mapping
    options:
      show_root_heading: false

## Transports

::: spakky.plugins.a2a.rest_transport
    options:
      show_root_heading: false

::: spakky.plugins.a2a.rest_transport.builder
    options:
      show_root_heading: false

::: spakky.plugins.a2a.grpc_transport
    options:
      show_root_heading: false

::: spakky.plugins.a2a.grpc_transport.builder
    options:
      show_root_heading: false

::: spakky.plugins.a2a.grpc_transport.handler
    options:
      show_root_heading: false

## Client와 Delegation

::: spakky.plugins.a2a.client
    options:
      show_root_heading: false

::: spakky.plugins.a2a.delegation
    options:
      show_root_heading: false

## Task Store

::: spakky.plugins.a2a.store.interfaces
    options:
      show_root_heading: false

::: spakky.plugins.a2a.store.task_store
    options:
      show_root_heading: false

## Plugin

::: spakky.plugins.a2a.post_processors.register_agent_servers
    options:
      show_root_heading: false

::: spakky.plugins.a2a.post_processors.mount_asgi
    options:
      show_root_heading: false

::: spakky.plugins.a2a.post_processors.register_grpc
    options:
      show_root_heading: false

::: spakky.plugins.a2a.main
    options:
      show_root_heading: false

## 에러

::: spakky.plugins.a2a.error
    options:
      show_root_heading: false
