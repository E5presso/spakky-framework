# AG-UI 어댑터

> 선언형 Agent를 AG-UI (Agent User Interaction) 프로토콜로 노출해, Agent 실행 이벤트를
> UI에 SSE (Server-Sent Events), HTTP streaming, WebSocket, stdio로 스트리밍하는 어댑터 가이드입니다.
> 렌더링(프런트엔드)은 범위 밖이며, 본 가이드는 와이어 프로토콜까지를 다룹니다.

`spakky-agui` plugin은 선언형 `@Agent`의 `AgentRunner.run_events()` 스트림을 AG-UI 이벤트로 투영하여
SSE, HTTP streaming, WebSocket, stdio로 노출합니다. 승인이 필요한 도구는 deferred-tool 방식의 HITL
(Human-in-the-loop) 흐름으로 표면화됩니다.

## 1. `@Agent` 선언

선언형 Agent는 spec과 `@agent_tool` 메서드만 선언하면 프레임워크가 실행 루프를 제공합니다
(자세한 내용은 [AI Agent 심화](agents-advanced.md)).

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

`@AGUICompatible(server_names=("weather",))`를 지정하면 `spakky-mcp`가 제공하는
`IAgentRunnerFactory`가 해당 external MCP server tool만 이 Agent run에 결합합니다. 비워두면
configured MCP server 전체를 사용합니다.

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
| `RUN_PAUSED` | `hitl_approval` deferred `TOOL_CALL_*` frame |
| `RUN_FINISHED` | `RUN_FINISHED` 또는 `RUN_ERROR` |
| `STEP_STARTED`/`STEP_FINISHED` | `STEP_STARTED`/`STEP_FINISHED` |
| `STATE_SNAPSHOT` | `STATE_SNAPSHOT` (설정 게이트) |
| `STATE_DELTA` | `STATE_DELTA` |
| `ARTIFACT` | `CUSTOM` (name=`artifact`) |

## 4. deferred-tool HITL 흐름

AG-UI에는 1급 승인 이벤트가 없습니다. 승인 요청은 `hitl_approval` 도구의 **deferred tool
call**로 표면화됩니다. core runner는 승인 필요 도구에서 멈출 때 `RunPausedEvent`를 방출하고,
projector는 이 pause를 `TOOL_CALL_START`/`TOOL_CALL_ARGS`/`TOOL_CALL_END` 프레임으로 바꿉니다.
결과 프레임은 일부러 보내지 않습니다.

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

## 매핑 충실도

도구·메시지·실행 이벤트 매핑은 `run_events()`를 통해 **완전 무손실(lossless)**입니다. 런너가
메시지/추론 delta, 도구 호출 `start`/`args-delta`/`end`/`result` 생명주기, run/step 경계를
각각 별개의 중립 `AgentEvent`로 native 방출하므로, 어댑터는 거친 yield를 재구성하지 않고
1:1로 투영합니다(과거 `AgentYield → AgentEvent` bridge는 제거되었습니다). reasoning을
지원하지 않는 모델에서는 `REASONING_DELTA`가 생략되고(graceful degrade), 현재 모델 루프가
생성하지 않는 `STATE_SNAPSHOT`/`STATE_DELTA`/`ARTIFACT`는 live 런에서 방출되지 않지만
projector는 taxonomy 완전성을 위해 이들 종류도 계속 처리합니다. `parentRunId`는 `RunAgentInput.parent_run_id`가
전달된 실행에서만 `RUN_STARTED`에 포함됩니다.

## API Reference

- [spakky-agui API Reference](../api/plugins/spakky-agui.md): endpoint, transport, projector, HITL helper 시그니처를 확인합니다.
- [spakky-agent API Reference](../api/core/spakky-agent.md): `AgentRunner.run_events()`, `RunAgentInput`, `AgentEvent`를 확인합니다.
