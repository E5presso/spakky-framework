# AI Agent 심화

> `spakky-agent`의 tool catalog, approval, durable execution, transport adapter, AG-UI/CopilotKit 연동을 다룹니다.

이 문서는 [AI Agent 개발](agents.md)을 읽은 뒤 보는 심화 가이드입니다. 여기서는 작은 Agent를 운영형 Agent로 확장할 때 필요한 선택지를 정리합니다.

## Tool 설계

Tool은 모델이 호출할 수 있는 애플리케이션 기능입니다. `@agent_tool`은 Python method의 signature를 읽어 schema를 만들고, risk, approval, evidence, idempotency metadata를 함께 보관합니다.

읽기 tool은 approval 없이 실행할 수 있도록 명시합니다.

```python
from dataclasses import dataclass
from typing import Protocol

from spakky.agent import (
    Agent,
    AgentExecutionSpec,
    EvidenceCapture,
    Idempotency,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
)


@dataclass(frozen=True, slots=True)
class WorkspaceReadResult:
    path: str
    content: str


class WorkspacePort(Protocol):
    def read_text(self, path: str) -> WorkspaceReadResult:
        ...


@Agent(spec=AgentExecutionSpec(name="code_assistant", objective="inspect files"))
class CodeAssistant:
    def __init__(self, workspace: WorkspacePort) -> None:
        self._workspace = workspace

    @agent_tool(
        schema_name="workspace.read",
        description="Read a text file from the bounded workspace.",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def workspace_read(self, path: str) -> WorkspaceReadResult:
        return self._workspace.read_text(path)
```

쓰기 tool은 state를 바꾸므로 approval 후보가 됩니다.

```python
@dataclass(frozen=True, slots=True)
class WorkspaceWriteResult:
    path: str
    bytes_written: int


@agent_tool(
    schema_name="workspace.write",
    description="Write a text file in the bounded workspace.",
    effects=ToolEffects.write_state(),
    idempotency=Idempotency.CONDITIONALLY_IDEMPOTENT,
    evidence=EvidenceCapture.STRUCTURED,
)
def workspace_write(self, path: str, content: str) -> WorkspaceWriteResult:
    return self._workspace.write_text(path, content)
```

`approval`을 생략하면 기본값은 `DERIVED`입니다. `ToolEffects.write_state()`, `external_side_effect()`, `destructive_action()`처럼 side effect가 있는 tool은 approval candidate가 됩니다.

| tool 종류 | 권장 metadata |
|-----------|---------------|
| 파일 읽기, 검색, git status/diff | `ToolEffects.read_only()`, `Idempotency.IDEMPOTENT`, `approval=NOT_REQUIRED` |
| 파일 쓰기, local state 변경 | `ToolEffects.write_state()`, `Idempotency.CONDITIONALLY_IDEMPOTENT` |
| shell command, 외부 API 호출 | `ToolEffects.external_side_effect()`, `Idempotency.NON_IDEMPOTENT` |
| patch 적용, 삭제, 되돌리기 어려운 변경 | `ToolEffects.destructive_action()` |
| 모델에게 raw output을 보내면 위험한 결과 | `evidence=SUMMARY` 또는 `evidence=REDACTED` |
| audit trail에 구조화 결과가 필요한 경우 | `evidence=STRUCTURED` |

`@agent_tool` signature는 schema의 정본입니다. Parameter와 return type은 annotation해야 합니다. `*args`, `**kwargs`, positional-only parameter, JSON schema로 표현할 수 없는 임의 object는 definition 단계에서 실패합니다.

## Tool catalog를 모델 요청에 넣기

`@Agent` metadata에는 발견된 tool catalog가 들어 있습니다.

```python
from spakky.agent import Agent

agent_metadata = Agent.get(CodeAssistant)
for descriptor in agent_metadata.tool_catalog.descriptors:
    print(descriptor.schema.name, descriptor.description)
```

Model request에 tool schema를 넣을 때는 descriptor를 `ModelToolSpec`으로 변환합니다.

```python
from spakky.agent import (
    Agent,
    JsonSchemaConstraint,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelToolChoice,
    ModelToolSpec,
    ToolCallingSpec,
)

tools = tuple(
    ModelToolSpec(
        name=descriptor.schema.name,
        description=descriptor.description,
        parameters=JsonSchemaConstraint(schema=descriptor.schema.input_schema),
        metadata={"tool_identity": descriptor.identity.key},
    )
    for descriptor in Agent.get(CodeAssistant).tool_catalog.descriptors
)

request = ModelRequest(
    messages=(ModelMessage(ModelMessageRole.USER, instruction),),
    tool_calling=ToolCallingSpec(tools=tools, choice=ModelToolChoice.AUTO),
)
```

Model adapter가 `ModelStreamEventKind.TOOL_CALL_CANDIDATE`를 내보내면 Agent는 보통 다음 순서로 처리합니다.

1. `call.name`으로 `AgentToolCatalog`에서 descriptor를 찾습니다.
2. `plan_agent_tool_approval()`로 approval이 필요한지 판단합니다.
3. 필요하면 `AgentYieldKind.APPROVAL`을 yield하고 decision signal을 기다립니다.
4. 승인되었거나 approval이 필요 없으면 `descriptor.bind_invocation(call.arguments)`로 argument를 검증합니다.
5. Python method를 호출합니다.
6. result를 `AgentYieldKind.TOOL`이나 evidence로 남깁니다.

```python
from spakky.agent import Agent, AgentYield, plan_agent_tool_approval

metadata = Agent.get(CodeAssistant)
descriptor = metadata.tool_catalog.by_schema_name(call.name)

approval = plan_agent_tool_approval(
    descriptor=descriptor,
    approval_id=f"approval:{state.id}:{call.name}",
    agent_state_id=state.id,
    agent_type="CodeAssistant",
    call_id=call.call_id,
)

if approval.requires_approval and approval.yield_item is not None:
    yield AgentYield(kind=approval.yield_item.kind, payload=approval.yield_item.payload)
    return

bound = descriptor.bind_invocation(call.arguments)
result = descriptor.callable(self, *bound.args, **bound.kwargs)
```

`bind_invocation()`은 model payload가 Python signature와 맞는지 검사합니다. 필수 인자 누락, 알 수 없는 인자, 중복 인자는 tool method가 실행되기 전에 `AgentToolBindingError`로 실패합니다.

## Approval, signal, cancel

Approval은 모든 tool 앞에서 묻는 기능이 아닙니다. Tool metadata에서 risk를 계산하고, side effect가 있는 boundary에서만 approval request를 만듭니다.

```python
from spakky.agent import AgentSignal, AgentSignalKind, ApprovalDecision

signals.append(
    AgentSignal(
        id="approval:run-1:workspace.write",
        agent_state_id="run-1",
        kind=AgentSignalKind.APPROVAL_DECISION,
        payload={
            "request_id": "approval:run-1:workspace.write",
            "decision": ApprovalDecision.APPROVE.value,
        },
    )
)
```

Signal은 실행 중 Agent에게 들어오는 외부 입력입니다.

| signal kind | 의미 |
|-------------|------|
| `USER_MESSAGE` | 실행 중 사용자가 추가 지시를 보냄 |
| `APPROVAL_DECISION` | approval request에 대한 approve/reject/modify/defer/cancel 결정 |
| `CANCEL` | 실행 취소 요청 |
| `RESUME` | 중단된 실행 재개 요청 |
| `STEERING_INSTRUCTION` | 실행 방향을 바꾸는 운영 지시 |
| `EXTERNAL_EVENT` | 외부 시스템에서 들어온 event |
| `SCHEDULER_WAKE_UP` | scheduler가 Agent를 깨움 |

Durable repository를 쓰는 경우 orchestration은 safe boundary에서 `consume_pending_agent_signals()`를 호출합니다. 이 helper는 pending queue를 append order로 읽고, 현재 Agent가 받아들일 수 있는 prefix만 consumed 처리합니다.

Cancel은 바로 terminal state로 덮어쓰는 flag가 아닙니다. 일반적인 흐름은 `begin_agent_cancellation()`으로 state를 `CANCELLING`으로 만들고, model stream/tool/delegate cleanup hook을 실행한 뒤 `complete_agent_cancellation()`으로 끝냅니다.

## Durable 실행과 repository

짧은 Agent는 repository 없이도 동작할 수 있습니다. 하지만 다음 중 하나를 쓰면 durable path입니다.

- `AgentExecutionSpec(recovery=RecoveryStrategy.ACTION_BOUNDARY)`
- `AgentExecutionSpec(accepted_signals=(...))`

Durable path에서는 bootstrap이 다음 repository port를 요구합니다.

| repository | 저장하는 것 |
|------------|-------------|
| `IAgentStateRepository` | `AgentState`: 현재 status, transition, current activity, input ref |
| `IAgentSignalRepository` | `AgentSignal`: user message, approval decision, cancel 같은 inbound queue |
| `IAgentEvidenceRepository` | `AgentEvidence`: tool/model/context 판단 근거와 action-boundary checkpoint |

운영에서는 `spakky-sqlalchemy[agent]` contribution을 사용합니다.

```bash
pip install "spakky-sqlalchemy[agent]"
```

이 contribution은 `spakky.contributions.spakky.agent` entry point로 SQLAlchemy repository와 table을 등록합니다. 운영용 in-memory fallback은 없습니다. Repository가 없는데 durable path를 선언하면 bootstrap에서 fail-fast해야 합니다.

```python
from spakky.agent import AgentExecutionLimits, AgentExecutionSpec, AgentSignalKind, RecoveryStrategy

spec = AgentExecutionSpec(
    name="code_assistant",
    objective="inspect and edit a workspace",
    recovery=RecoveryStrategy.ACTION_BOUNDARY,
    accepted_signals=(
        AgentSignalKind.USER_MESSAGE,
        AgentSignalKind.APPROVAL_DECISION,
        AgentSignalKind.CANCEL,
    ),
    limits=AgentExecutionLimits(timeout_seconds=300),
)
```

Restart 후에는 `plan_agent_resume(state, evidence, pending_signals)`가 다음 동작을 결정합니다.

| 상황 | resume action |
|------|---------------|
| 이미 완료된 action boundary | 완료된 action을 다시 실행하지 않고 skip |
| idempotent action이 incomplete | retry 가능 |
| non-idempotent/unknown action이 incomplete | 사람 확인 필요 |
| approval wait 중 재시작 | approval decision을 기다림 |

Evidence는 append-only입니다. Tool result를 수정하거나 삭제해서 history를 고치지 않고, redaction, correction, context digest 갱신도 새 evidence를 append하는 방식으로 표현합니다.

## FastAPI, WebSocket, SSE, CLI

Agent 전용 inbound package는 필요하지 않습니다. 기존 `spakky-fastapi`나 `spakky-typer` controller에서 Agent를 resolve하고 stream을 변환합니다.

WebSocket adapter의 핵심은 다음과 같습니다.

```python
@websocket("/agents/code/ws")
async def code_socket(self, websocket: WebSocket) -> None:
    command = await websocket.receive_json()
    agent = self._container.get(CodeAssistant)
    async for item in agent.execute(command):
        await websocket.send_json(agent_yield_to_event(item))
```

SSE는 단방향 server-to-client stream입니다. 사용자의 새 메시지나 approval decision을 같은 연결로 받을 수 없으므로, SSE endpoint와 별도의 POST endpoint를 함께 둡니다.

- `POST /agents/code/sse`: 실행을 시작하고 `AgentYield`를 SSE frame으로 흘려보냅니다.
- `POST /agents/code/signals`: approval decision, cancel, user message를 `IAgentSignalRepository`에 append합니다.

## AG-UI와 CopilotKit

AG-UI는 `AgentYield`와 다른 wire protocol입니다. 공식 AG-UI HTTP agent는 POST body로 `threadId`, `runId`, `messages`, `state`, `tools`, `context`, `forwardedProps`를 받고, 응답은 `text/event-stream`으로 `data: {"type": ...}` frame을 흘려보냅니다.

현재 Spakky 상태를 정확히 말하면 다음과 같습니다.

- `spakky-agent`는 AG-UI와 개념적으로 맞는 stream/event building block을 제공합니다.
- `AgentYield` 자체는 AG-UI event가 아닙니다.
- 현재 repository에는 built-in `spakky-agent-agui` adapter나 AG-UI event class가 없습니다.
- CopilotKit은 AG-UI `HttpAgent`로 Spakky backend에 붙을 수 있지만, Spakky 쪽에 AG-UI HTTP/SSE adapter endpoint를 구현해야 합니다.

권장 mapping은 다음과 같습니다.

| Spakky `AgentYieldKind` | AG-UI event | 설명 |
|-------------------------|-------------|------|
| stream 시작 전 | `RUN_STARTED` | `threadId`와 `runId`는 AG-UI request 값을 사용합니다. |
| 첫 `TOKEN` 전 | `TEXT_MESSAGE_START` | assistant message id를 생성합니다. |
| `TOKEN` | `TEXT_MESSAGE_CONTENT` | `Token.text`를 `delta`로 보냅니다. |
| `PROGRESS` | `CUSTOM` | Spakky progress는 AG-UI step lifecycle과 1:1이 아니므로 `CUSTOM`이 안전합니다. |
| `TOOL` result | `TOOL_CALL_RESULT` | `Tool.result`를 JSON string 또는 text content로 보냅니다. |
| `APPROVAL` | `CUSTOM` 또는 `STATE_DELTA` | AG-UI core에는 Spakky approval 전용 event가 없으므로 frontend 약속이 필요합니다. |
| `FINAL` | `TEXT_MESSAGE_END` + `RUN_FINISHED` | token message가 열려 있으면 먼저 닫습니다. |
| `ERROR` | `RUN_ERROR` | `Error.message`를 AG-UI error message로 보냅니다. |

정리하면 CopilotKit으로 붙일 수는 있습니다. 단, Spakky endpoint가 CopilotKit `HttpAgent`가 기대하는 AG-UI request/response를 구현해야 합니다. `AgentYield`를 그대로 SSE로 흘리는 Spakky-native endpoint는 CopilotKit용 endpoint가 아닙니다.

## 테스트 전략

Agent 테스트는 실제 LLM에 의존하지 않는 것이 좋습니다.

| 테스트 대상 | 권장 double |
|-------------|-------------|
| model stream 처리 | scripted `IAgentModel` fake |
| tool 호출 | in-memory workspace/shell/git port fake |
| approval | in-memory `IAgentSignalRepository`에 decision signal append |
| durable state | in-memory repository double 또는 SQLAlchemy test DB |
| resume | 저장된 state/evidence/signal을 만들고 `plan_agent_resume()` 결과 확인 |

이 repository의 runnable reference는 다음 명령으로 확인합니다.

```bash
cd core/spakky-agent
uv run pytest tests/acceptance/test_code_assistant_demo_acceptance.py -q --no-cov
```

이 테스트는 실제 vLLM server 없이 scripted model stream으로 CodeAssistant 흐름을 검증합니다.

## 운영 체크리스트

- `@Agent.execute()` input과 return/yield type이 모두 annotate되어 있습니다.
- Agent가 provider SDK, DB client, HTTP framework를 직접 import하지 않고 port/interface에 의존합니다.
- Model backend는 `IAgentModel` adapter 뒤에 있습니다.
- 모든 model-callable capability는 `@agent_tool`로 선언되어 schema, risk, idempotency, evidence metadata가 있습니다.
- Write/network/destructive tool은 approval path가 있습니다.
- Durable path를 쓰면 state/signal/evidence repository contribution이 등록되어 있습니다.
- Inbound adapter는 `AgentYieldKind.APPROVAL`을 사용자 decision signal로 연결합니다.
- CopilotKit 연동 endpoint는 Spakky-native `AgentYield` JSON이 아니라 AG-UI `type` event stream을 반환합니다.
- Cancel은 cancellation lifecycle로 처리하고 즉시 terminal state로 덮지 않습니다.
- Evidence는 append-only로 남깁니다.
- 테스트는 실제 model server 없이 scripted stream으로 주요 branch를 검증합니다.

## 더 볼 곳

- [CodeAssistant 에이전트 예제](agent-code-assistant.md): workspace/shell/git tool, approval, evidence, cancel/resume을 한 execution으로 연결한 runnable demo입니다.
- [spakky-agent API Reference](../api/core/spakky-agent.md): public class와 helper의 상세 signature를 확인합니다.
- [spakky-vllm API Reference](../api/plugins/spakky-vllm.md): OpenAI-compatible vLLM model adapter를 확인합니다.
- [spakky-sqlalchemy API Reference](../api/plugins/spakky-sqlalchemy.md): durable agent repository contribution을 확인합니다.
