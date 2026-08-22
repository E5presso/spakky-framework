# AG-UI 어댑터

> 선언형 Agent를 AG-UI (Agent User Interaction) 프로토콜로 노출해, Agent 실행 이벤트를
> UI에 SSE (Server-Sent Events), HTTP streaming, WebSocket, stdio로 스트리밍하는 어댑터 가이드입니다.
> 렌더링(프런트엔드)은 범위 밖이며, 본 가이드는 와이어 프로토콜까지를 다룹니다.

`spakky-agui` plugin은 선언형 `@Agent`의 `AgentRunner.run_events()` 스트림을 AG-UI 이벤트로 투영하여
SSE, HTTP streaming, WebSocket, stdio로 노출합니다. 승인이 필요한 도구는 deferred-tool 방식의 HITL
(Human-in-the-loop) 흐름으로 표면화됩니다.

## 1. `@Agent` 선언

선언형 Agent는 spec과 `@agent_tool` 메서드만 선언하면 프레임워크가 bounded iterative
model/tool 실행을 제공합니다. Tool result는 다음 model request에 재주입되고 AG-UI는
각 `model-N`/`tool-N` step과 마지막 `RUN_FINISHED`를 같은 run stream에 투영합니다.
자세한 경계는 [AI Agent 심화](agents-advanced.md)를 확인하세요.

```python
from spakky.agent import (
    Agent, AgentExecutionSpec, AgentSignalKind, RecoveryStrategy,
    EvidenceCapture, Idempotency, ToolApprovalRequirement, ToolEffects, agent_tool,
    IAgentEvidenceRepository, IAgentModel, IAgentSignalRepository,
    IAgentStateRepository,
)


@Agent(
    spec=AgentExecutionSpec(
        name="assistant",
        objective="answer with tools",
        accepted_signals=(
            AgentSignalKind.APPROVAL_DECISION,
        ),
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
    )
)
class Assistant:
    def __init__(
        self,
        model: IAgentModel,
        states: IAgentStateRepository,
        signals: IAgentSignalRepository,
        evidence: IAgentEvidenceRepository,
    ) -> None:
        self._model = model
        self._states = states
        self._signals = signals
        self._evidence = evidence

    @agent_tool(
        schema_name="note.write",
        description="Write a note after human approval.",
        effects=ToolEffects.write_state(),
        idempotency=Idempotency.CONDITIONALLY_IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.REQUIRED,
    )
    def note_write(self, topic: str) -> str:
        """Write a note for a topic after approval."""
        return f"write:{topic}"
```

## 2. endpoint 마운트

AG-UI 노출은 `@Agent` 위에 `@AGUICompatible` tag를 쌓아 선언합니다. plugin은
`AgUiConfig`, `AgUiAgentRegistry`, FastAPI mount post-processor를 등록하고, post-processor가
marked Agent와 FastAPI Pod를 발견해 SSE/HTTP streaming/WebSocket route를 자동으로 붙입니다.
애플리케이션 코드는 `run_driver_factory`나 `add_agui_endpoint()`를 호출하지 않습니다.

```python
from fastapi import FastAPI
from spakky.agent import Agent, AgentExecutionSpec, IAgentModel
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.agui import AGUICompatible


@Pod(name="fastapi_app")
def fastapi_app() -> FastAPI:
    return FastAPI()


@AGUICompatible()
@Agent(spec=AgentExecutionSpec(name="assistant", objective="answer with tools"))
class Assistant:
    def __init__(self, model: IAgentModel) -> None:
        self._model = model


application = SpakkyApplication(ApplicationContext())
application.load_plugins().scan(my_app).start()
app = application.container.get(FastAPI)
```

여러 Agent를 노출할 때는 path 충돌을 피하도록 각 Agent에 경로를 선언합니다.

```python
@AGUICompatible(
    sse_path="/agents/researcher/agui",
    http_stream_path="/agents/researcher/agui/stream",
    websocket_path="/agents/researcher/agui/ws",
)
@Agent(spec=AgentExecutionSpec(name="researcher"))
class Researcher:
    ...
```

AG-UI annotation에는 MCP 서버명을 굽지 않습니다. 서비스나 사용자가 run마다 붙일 외부 MCP
server를 고르면 AG-UI `forwardedProps.mcp`가 core `RunAgentInput.metadata["mcp"]`로 변환되고,
`spakky-mcp`가 그 run에만 toolset을 합류시킵니다.

모델을 고를 때는 operator가 `LlmConfig.models`에 등록한 opaque logical ref만
전달합니다. AG-UI wire shape는 `forwardedProps.modelSelection.modelRef`이며 내부
object는 정확히 `modelRef` 하나만 가져야 합니다. Provider, profile, physical model,
selection metadata는 wire 선택 필드가 아닙니다. Catalog 등록 형식은
[LLM 모델 라우팅](llm-routing.md)을 확인하세요.

```json
{
  "threadId": "conv-1",
  "runId": "run-1",
  "state": null,
  "messages": [{"id": "u1", "role": "user", "content": "check the issue"}],
  "tools": [],
  "context": [],
  "forwardedProps": {
    "modelSelection": {
      "modelRef": "support/primary"
    },
    "mcp": {"servers": ["github"]}
  }
}
```

활성 `IAgentModel`이 catalog-aware `LlmAgentModel`일 때 `modelSelection`이 없으면 그
router의 `default_model`을 사용합니다. Object가 아니거나,
`modelRef`가 blank/non-string이거나, legacy `provider`/`profile`/`model`을 포함하거나,
알 수 없는 nested field가 있으면 `AgUiRunResolutionError`로 거부합니다. Well-formed하지만
catalog에 없는 ref는 protocol shape 오류가 아닙니다. `LlmAgentModel.stream()`이
`llm_model_selection_invalid` model error를 내고 runner가 terminal run error로 바꾸므로,
AG-UI에는 같은 code의 `RUN_ERROR`로 표면화됩니다. `/`는 provider 구분자로 해석되지
않습니다.

SSE 클라이언트는 `POST /agui` body로 AG-UI `RunAgentInput`을 보내고 `text/event-stream`
응답을 받습니다. HTTP streaming 클라이언트는 `POST /agui/stream` body로 같은 입력을 보내고
`application/x-ndjson` chunk를 받습니다. WebSocket 클라이언트는 `/agui/ws`에 연결한 뒤 같은 `RunAgentInput` JSON을
text/JSON message로 보내고, AG-UI encoded event frame을 text message로 순서대로 받습니다.
같은 WebSocket 연결에서 후속 `RunAgentInput`을 보내 승인 결정(`forwardedProps.approvalDecision`
또는 deferred tool-result message)을 전달할 수 있습니다.

CLI나 MCP-style local bridge가 AG-UI payload를 stdio로 주고받아야 하면
`AgUiStdioCommand`를 사용합니다. 입력은 AG-UI `RunAgentInput` JSON 한 건이고, 출력은
AG-UI encoded event payload를 한 줄에 하나씩 씁니다.
stdio 전용 host는 lower-level `RunDriverFactory`를 `AgUiStdioCommand`에 전달합니다. 일반
FastAPI SSE/HTTP/WebSocket 노출은 `@AGUICompatible` 선언만 사용합니다.

### 설정

| 환경변수 | 기본값 | 목적 |
|---------|--------|------|
| `SPAKKY_AGUI_SSE_PATH` | `/agui` | SSE endpoint 경로 |
| `SPAKKY_AGUI_WEBSOCKET_PATH` | `/agui/ws` | WebSocket endpoint 경로 |
| `SPAKKY_AGUI_HTTP_STREAM_PATH` | `/agui/stream` | NDJSON HTTP streaming endpoint 경로 |
| `SPAKKY_AGUI_EMIT_STATE_SNAPSHOT` | `true` | `STATE_SNAPSHOT` 투영 여부 |
| `SPAKKY_AGUI_MESSAGES_SNAPSHOT_ENABLED` | `false` | `RUN_FINISHED` 직전 `MESSAGES_SNAPSHOT` 방출 여부 |

## 3. 이벤트 매핑 (중립 → AG-UI)

| 중립 `AgentEvent` | AG-UI 이벤트 |
|------------------|-------------|
| `MESSAGE_DELTA` | `TEXT_MESSAGE_START` + `TEXT_MESSAGE_CONTENT` (빈 delta 생략) |
| `REASONING_DELTA` | `REASONING_START` + `REASONING_MESSAGE_START` + `REASONING_MESSAGE_CONTENT` |
| `TOOL_CALL_START` | `TOOL_CALL_START` |
| `TOOL_CALL_ARGS_DELTA` | `TOOL_CALL_ARGS` |
| `TOOL_CALL_END` | `TOOL_CALL_END` |
| `TOOL_CALL_RESULT` | `TOOL_CALL_RESULT` |
| `RUN_STARTED` | `RUN_STARTED` |
| approval ID가 있는 `RUN_PAUSED` | `hitl_approval` deferred `TOOL_CALL_*` frame |
| `RUN_FINISHED` | `RUN_FINISHED` 또는 `RUN_ERROR` |
| `STEP_STARTED`/`STEP_FINISHED` | `STEP_STARTED`/`STEP_FINISHED` |
| `STATE_SNAPSHOT` | `STATE_SNAPSHOT` (설정 게이트) |
| `STATE_DELTA` | `STATE_DELTA` |
| `ARTIFACT` | `CUSTOM` (name=`artifact`) |

Provider가 candidate만 보내고 fine-grained tool frame을 생략하면 core runner가 없는
`TOOL_CALL_START`/`TOOL_CALL_END`만 합성하므로 AG-UI에서도 balanced tool lifecycle을
받습니다. 이미 provider가 보낸 frame은 중복하지 않습니다. Signal hook이나 기본 user
message 처리의 `Progress`는 core에서 `ArtifactEvent(name="signal_progress")`가 된 뒤 AG-UI
`CUSTOM` artifact로 투영됩니다. Non-Progress hook yield는
`agent_signal_projection_unsupported` `RUN_ERROR`입니다.

## 4. deferred-tool HITL 흐름

AG-UI에는 1급 승인 이벤트가 없습니다. 승인 요청은 `hitl_approval` 도구의 **deferred tool
call**로 표면화됩니다. core runner는 승인 필요 도구에서 멈출 때 `RunPausedEvent`를 방출하고,
projector는 이 pause를 `TOOL_CALL_START`/`TOOL_CALL_ARGS`/`TOOL_CALL_END` 프레임으로 바꿉니다.
결과 프레임은 일부러 보내지 않습니다.

이 projection은 approval-required pause에만 동작합니다. `RunPausedEvent.approval_id`가
`None`인 authentication-required 또는 일반 user-input pause는 deferred approval로
추측하지 않고 `AgUiPendingApprovalError`를 발생시킵니다. 현재 AG-UI adapter에는 이 두
pause 종류를 위한 별도 wire mapping이 없으므로, 그런 run을 AG-UI에 노출하려면 먼저
protocol-specific mapping을 확장해야 합니다.

1. 런너가 승인 필요 도구에서 멈추면 `run_events()`가 `RunPausedEvent`를 내보냅니다.
   `AgUiProjector`는 이를 `hitl_approval` deferred tool frame으로 투영합니다.
2. 클라이언트가 사람의 결정을 수집해 다음 `RunAgentInput`에 담아 다시 전송합니다 (SSE에서는
   POST, WebSocket에서는 같은 연결의 후속 message; deferred call id를 향한 tool-result 메시지,
   또는 `forwardedProps.approvalDecision`). 결정 payload는
   `{"request_id": "<approval id>", "decision": "approve|reject|modify|defer|cancel"}` 형태여야 하며,
   `modified_payload`와 `comment`를 선택적으로 포함할 수 있습니다.
3. `ingest_decision`이 결정을 디코딩하여 durable signal queue에 `APPROVAL_DECISION`
   signal로 적재하면 런너가 `run_events()`를 다시 돌며 재개합니다. `APPROVE`/`MODIFY`는
   도구를 진행시키고, `REJECT`는 종료로 이어집니다.

## 매핑 충실도와 제한

`run_events()`는 protocol adapter가 coarse `AgentYield`를 역추론하지 않도록 세분화된
source event를 제공합니다. 그렇다고 AG-UI projection이 무손실 또는 1:1인 것은 아닙니다.
하나의 message/reasoning delta가 start/content/end lifecycle로 확장될 수 있고, 빈 delta는
생략됩니다. 각 `STEP_FINISHED` 앞에서 projector가 열린 text/reasoning/tool frame을 먼저
닫으므로 `model-1`과 `model-2`의 message lifecycle이 섞이지 않습니다. Stream 종료 시
남은 frame은 `finish()`가 닫습니다. `RUN_FINISHED`는
성공 시 `metadata["output"]`만 result로 사용하고 오류는 code/message만 전달합니다.

예를 들어 tool round 하나는 `model-1` message frame → `model-1` step finish →
`tool-1` result → `model-2` message frame → `model-2` step finish → 단일
`RUN_FINISHED` 순서입니다. Message ID도 각각
`{run_id}:model-1:message`, `{run_id}:model-2:message`로 분리됩니다.

Reasoning을 지원하지 않는 선택 route에서는 `REASONING_DELTA`가 생략됩니다. State
snapshot은 설정 gate를 따르고, artifact는 native artifact event가 없어 `CUSTOM`으로
변환됩니다. 앞 절처럼 approval이 아닌 pause는 현재 projection할 수 없습니다.
`parentRunId`는 `RunAgentInput.parent_run_id`가 전달된 실행의 `RUN_STARTED`에만 포함됩니다.
Canonical cancel signal은 `code="cancelled"`와 `state`, `signal_id`, optional
`requested_by` metadata를 가진
`RUN_ERROR` 하나로 끝나며 success `RUN_FINISHED`를 추가하지 않습니다.

Agent가 `output_type`을 선언하면 core `RunFinishedEvent.metadata["output"]`의 JSON-safe
materialized value가 AG-UI `RUN_FINISHED.result`가 됩니다. Python BaseModel/dataclass
instance 자체를 wire에 넣지는 않습니다. `output_type`이 없는 기존 Agent는 core event에
`output` key가 없으므로 AG-UI result도 `null`로 유지됩니다.
Structured capability/missing/ambiguous/invalid terminal은 result로 내보내지 않고 해당
`agent_structured_output_*` code의 `RUN_ERROR`입니다.

AG-UI request의 protocol-native `context` 배열은 현재 core `AgentContext`로 자동 매핑되지
않습니다. Typed dynamic context가 필요한 exposed Agent는 constructor-injected
`IAgentContextProvider`를 사용합니다.

## API Reference

- [spakky-agui API Reference](../api/plugins/spakky-agui.md): endpoint, transport, projector, HITL helper 시그니처를 확인합니다.
- [spakky-agent API Reference](../api/core/spakky-agent.md): `AgentRunner.run_events()`, `RunAgentInput`, `AgentEvent`를 확인합니다.
