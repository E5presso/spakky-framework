# AI Agent 개발

이 문서는 `spakky-agent`로 AI agent를 처음 만드는 사용자를 위한 guide입니다. API 이름을 먼저 외우는 문서가 아니라, 각 구성요소가 무엇이고 왜 필요한지 이해한 뒤 작은 agent에서 운영형 agent까지 확장하는 흐름으로 읽습니다.

`spakky-agent`는 완성된 agent runtime이나 LLM SDK wrapper가 아닙니다. 핵심은 **Agent를 Spakky application component로 모델링하기 위한 계약과 helper**입니다. 즉, 사용자는 agent workflow를 `@Agent` class로 작성하고, model backend는 `IAgentModel` adapter 뒤로 숨기고, model이 사용할 기능은 `@agent_tool` method로 노출하고, 긴 실행의 상태와 사용자 입력은 state/signal/evidence repository로 다룹니다.

## 먼저 알아야 할 그림

가장 단순한 실행 흐름은 다음과 같습니다.

```text
Client / HTTP / CLI
        |
        v
Inbound adapter
        |
        | container.get(MyAgent)
        v
@Agent class
        |
        | builds ModelRequest
        v
IAgentModel adapter  ----->  vLLM or another model backend
        |
        | ModelStreamEvent(token/tool/done/error)
        v
@Agent.execute()
        |
        | AgentYield(token/progress/approval/final/...)
        v
Inbound adapter sends events back to the client
```

Tool과 durable execution을 추가하면 흐름이 이렇게 넓어집니다.

```text
Model emits tool call
        |
        v
AgentToolCatalog finds @agent_tool descriptor
        |
        v
approval helper decides proceed or wait
        |
        +-- approval required --> AgentYield(APPROVAL) --> user decision signal
        |
        +-- proceed -----------> bind arguments --> call Python method
                                  |
                                  v
                           append evidence / checkpoint
```

여기서 중요한 점은 `spakky-agent`가 모든 loop를 마법처럼 대신 돌려주지 않는다는 것입니다. Spakky가 제공하는 것은 component 등록, 타입 계약, schema 추출, approval/recovery/signal/evidence helper입니다. 실제 orchestration loop는 application 또는 예제처럼 agent class 안에서 작성합니다.

## 구성요소 사전

처음 볼 때 헷갈리는 이름들을 먼저 정리합니다.

| 이름 | 무엇인가 | 사용자가 하는 일 | 프레임워크가 해주는 일 |
| --- | --- | --- | --- |
| `@Agent` | Agent workflow class를 Spakky Pod로 등록하는 stereotype | class를 만들고 `execute()`를 구현 | scan, constructor DI, `execute()` 계약 검증, tool catalog discovery |
| `AgentExecutionSpec` | agent 실행 의미를 선언하는 metadata | 이름, 목적, timeout, signal, recovery 전략 선언 | durable repository 필요 여부 계산, bootstrap validation에 사용 |
| `execute()` | agent의 public 실행 entrypoint | input을 받고 model/tool/state 흐름을 작성 | 반환/yield type과 parameter shape 검증 |
| `AgentYield` | caller에게 흘려보내는 typed event | token, progress, approval, final 등을 yield | inbound adapter가 transport로 투영할 수 있는 공통 vocabulary 제공 |
| `IAgentModel` | model backend outbound port | agent는 이 interface만 의존 | vLLM 같은 provider adapter가 구현할 안정된 계약 제공 |
| `ModelRequest` | model에게 보낼 provider-neutral 요청 | system/user message, tool schema, sampling 설정 구성 | provider SDK와 agent core를 분리 |
| `ModelStreamEvent` | model adapter가 돌려주는 provider-neutral stream event | token/tool call/done/error를 해석해 `AgentYield`로 변환 | backend별 SSE/HTTP 응답을 공통 enum으로 정규화 |
| `@agent_tool` | model이 호출할 수 있는 Python method marker | method signature, 설명, risk, approval, evidence metadata 작성 | JSON schema 추출, catalog 등록, argument binding 검증 |
| `AgentToolCatalog` | agent class에서 발견된 tool 목록 | model request에 tool schema로 전달 | schema name lookup, duplicate 검증 |
| `AgentSignal` | 실행 중 외부에서 들어오는 자극 | user message, approval decision, cancel 등을 append | signal kind와 payload를 typed queue로 다룸 |
| `AgentState` | 긴 실행의 현재 lifecycle 상태 | state id와 status를 저장/갱신 | resume, cancellation, approval wait 판단에 사용 |
| `AgentEvidence` | 판단 근거와 checkpoint를 남기는 append-only artifact | tool result, boundary checkpoint, summary 등을 append | recovery와 audit trail의 공통 단위 제공 |
| repository ports | durable state/signal/evidence 저장소 interface | 운영에서 provider contribution 설치 | core가 특정 DB를 import하지 않게 함 |

## 언제 `@UseCase` 대신 `@Agent`를 쓰나

다음 중 하나라도 필요하면 `@Agent`가 적합합니다.

- LLM token이나 진행 상태를 HTTP, WebSocket, CLI로 streaming해야 한다.
- Model이 호출할 수 있는 tool 목록을 Python method signature에서 만들고 싶다.
- 파일 쓰기, shell 실행, 외부 API 호출 같은 위험 boundary 앞에서 사용자 승인을 받아야 한다.
- 실행 중 사용자의 추가 메시지, 승인/거절, 취소 요청을 받을 수 있어야 한다.
- 오래 걸리는 실행을 중간 checkpoint에서 재개하거나 audit evidence를 남겨야 한다.

반대로 단순히 한 번의 요청에서 deterministic business logic만 실행한다면 일반 `@UseCase`가 더 단순합니다.

## 패키지 선택

Agent contract만 실험할 때는 `spakky-agent`만 설치합니다.

```bash
pip install spakky-agent
```

로컬 vLLM과 durable repository까지 쓰는 구성은 model adapter와 persistence contribution을 함께 설치합니다.

```bash
pip install spakky-agent spakky-vllm "spakky-sqlalchemy[agent]"
```

패키지 역할은 이렇게 나뉩니다.

| 패키지 | 역할 |
| --- | --- |
| `spakky-agent` | `@Agent`, `AgentYield`, model/tool/state/signal/evidence 계약 |
| `spakky-vllm` | OpenAI-compatible vLLM endpoint를 `IAgentModel`로 감싸는 adapter |
| `spakky-sqlalchemy[agent]` | 운영용 `IAgentStateRepository`, `IAgentSignalRepository`, `IAgentEvidenceRepository` contribution |
| `spakky-fastapi` / `spakky-typer` | agent 전용 package가 아니라 기존 inbound adapter로 agent stream을 노출 |

## 1. 가장 작은 Agent 만들기

먼저 LLM도 tool도 없는 agent를 만듭니다. 목적은 `@Agent`가 일반 Spakky component처럼 constructor DI를 받고 `execute()` stream을 반환한다는 점을 확인하는 것입니다.

```python
from collections.abc import AsyncGenerator

from spakky.agent import Agent, AgentExecutionSpec, AgentYield, AgentYieldKind, Final
from spakky.core.pod.annotations.pod import Pod


@Pod()
class AnswerService:
    def answer(self, command: str) -> str:
        return f"handled:{command}"


@Agent(spec=AgentExecutionSpec(name="simple_agent", objective="handle one command"))
class SimpleAgent:
    def __init__(self, answers: AnswerService) -> None:
        self._answers = answers

    async def execute(
        self,
        command: str,
    ) -> AsyncGenerator[AgentYield[Final[str]], None]:
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(output=self._answers.answer(command), metadata={}),
        )
```

이 코드에서 각 줄의 의미는 다음과 같습니다.

| 코드 | 의미 |
| --- | --- |
| `@Agent(...)` | 이 class를 agent workflow component로 등록합니다. `@Pod`처럼 scan 대상입니다. |
| `AgentExecutionSpec` | agent 이름과 목적처럼 코드만으로 알 수 없는 실행 의미를 적습니다. |
| `__init__(..., answers: AnswerService)` | 일반 Spakky constructor DI입니다. Agent도 dependency를 직접 만들지 않습니다. |
| `execute(command: str)` | agent 실행 entrypoint입니다. 인자는 type annotation이 필요합니다. |
| `AgentYieldKind.FINAL` | 실행이 끝났음을 caller에게 알리는 event입니다. |
| `Final(output=...)` | 최종 결과 payload입니다. inbound adapter는 이 값을 HTTP/CLI/WebSocket 응답으로 바꿉니다. |

`execute()` 계약은 bootstrap 시 검증됩니다. `execute()`가 없거나, parameter annotation이 없거나, `*args`/`**kwargs`를 쓰거나, generator가 `AgentYield`가 아닌 값을 yield하도록 annotation하면 definition error가 납니다.

## 2. Agent stream을 client 응답으로 바꾸기

Agent는 HTTP, WebSocket, CLI를 직접 알지 않습니다. Inbound adapter가 agent를 container에서 꺼내고 `AgentYield`를 transport event로 바꿉니다.

```python
from spakky.agent import AgentYieldKind

agent = container.get(SimpleAgent)

async for item in agent.execute("summarize this file"):
    if item.kind is AgentYieldKind.FINAL:
        return {"result": item.payload.output}
```

Streaming UI라면 token과 progress도 그대로 보냅니다.

```python
async for item in agent.execute(command):
    if item.kind is AgentYieldKind.TOKEN:
        await websocket.send_text(item.payload.text)
    elif item.kind is AgentYieldKind.PROGRESS:
        await websocket.send_json({"progress": item.payload.message})
    elif item.kind is AgentYieldKind.FINAL:
        await websocket.send_json({"result": item.payload.output})
```

`AgentYieldKind`는 agent와 inbound adapter 사이의 공통 언어입니다.

| kind | payload class | 언제 쓰나 |
| --- | --- | --- |
| `TOKEN` | `Token` | model token delta를 즉시 보여줄 때 |
| `PROGRESS` | `Progress` | "tool 준비 중", "resume 계획 중" 같은 상태를 보여줄 때 |
| `TOOL` | `Tool` | tool call 또는 tool result를 UI/audit에 노출할 때 |
| `EVIDENCE` | `Evidence` | 저장된 evidence reference를 caller에게 알릴 때 |
| `APPROVAL` | `Approval` | 사용자 승인이 필요해 실행을 멈출 때 |
| `FINAL` | `Final[T]` | 최종 결과를 반환할 때 |
| `ERROR` | `Error` | recoverable 또는 terminal error를 구조화해 보낼 때 |
| `CANCEL` | `Cancel` | 취소 요청이 반영되었음을 알릴 때 |

## 3. Model을 붙이기

LLM backend는 agent가 직접 import하지 않습니다. Agent는 `IAgentModel`만 알고, 실제 provider adapter가 `complete()`와 `stream()`을 구현합니다.

```python
from collections.abc import AsyncGenerator

from spakky.agent import (
    Agent,
    AgentExecutionSpec,
    AgentYield,
    AgentYieldKind,
    Final,
    IAgentModel,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelStreamEventKind,
    Token,
)


@Agent(spec=AgentExecutionSpec(name="answer_agent", objective="answer questions"))
class AnswerAgent:
    def __init__(self, model: IAgentModel) -> None:
        self._model = model

    async def execute(
        self,
        question: str,
    ) -> AsyncGenerator[AgentYield[object], None]:
        request = ModelRequest(
            messages=(
                ModelMessage(ModelMessageRole.SYSTEM, "Answer as a concise assistant."),
                ModelMessage(ModelMessageRole.USER, question),
            )
        )
        answer: list[str] = []
        async for event in self._model.stream(request):
            if event.kind is ModelStreamEventKind.TOKEN_DELTA:
                text = event.token_delta or ""
                answer.append(text)
                yield AgentYield(kind=AgentYieldKind.TOKEN, payload=Token(text))
            elif event.kind is ModelStreamEventKind.DONE:
                yield AgentYield(
                    kind=AgentYieldKind.FINAL,
                    payload=Final(output="".join(answer), metadata={}),
                )
```

`ModelRequest`와 `ModelStreamEvent`는 provider-neutral 계약입니다.

| 타입 | 설명 |
| --- | --- |
| `ModelMessage` | system/user/assistant/tool/evidence message를 표현합니다. |
| `SamplingOptions` | temperature, top_p, max_tokens 같은 portable sampling 값을 담습니다. |
| `ToolCallingSpec` | model에게 제공할 tool schema 목록과 tool choice 전략을 담습니다. |
| `ModelStreamEventKind.TOKEN_DELTA` | provider가 보낸 token 조각입니다. |
| `ModelStreamEventKind.TOOL_CALL_CANDIDATE` | model이 tool 호출을 제안했다는 event입니다. |
| `ModelStreamEventKind.ERROR` | provider 오류를 agent core의 `ModelError`로 정규화한 event입니다. |
| `ModelStreamEventKind.DONE` | stream 종료 event입니다. |

운영에서 vLLM을 쓰면 `spakky-vllm` adapter를 주입합니다.

```python
from spakky.plugins.vllm.client import HttpxVllmChatClient
from spakky.plugins.vllm.config import VllmConfig
from spakky.plugins.vllm.model import VllmAgentModel

model = VllmAgentModel(VllmConfig(), HttpxVllmChatClient())
```

테스트에서는 network가 없는 scripted `IAgentModel` fake를 만들어 token/tool event를 원하는 순서로 내보내면 됩니다.

## 4. Tool을 설계하기

Tool은 model이 호출할 수 있는 application capability입니다. `@agent_tool`은 Python method를 다음 정보와 함께 등록합니다.

- model-facing schema name
- 사람이 읽는 설명
- method signature에서 추출한 input/output JSON schema
- read/write/network/destructive 같은 risk metadata
- idempotency와 resume metadata
- evidence capture 전략
- approval 필요 여부

읽기 tool 예시는 다음과 같습니다.

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

쓰기 tool은 metadata가 달라집니다.

```python
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

Tool metadata는 이렇게 고릅니다.

| tool 종류 | 권장 metadata |
| --- | --- |
| 파일 읽기, 검색, git status/diff | `ToolEffects.read_only()`, `Idempotency.IDEMPOTENT`, `approval=NOT_REQUIRED` |
| 파일 쓰기, local state 변경 | `ToolEffects.write_state()`, `Idempotency.CONDITIONALLY_IDEMPOTENT` |
| shell command, 외부 API 호출 | `ToolEffects.external_side_effect()`, `Idempotency.NON_IDEMPOTENT` |
| patch 적용, 삭제, 되돌리기 어려운 변경 | `ToolEffects.destructive_action()` |
| model에게 raw output을 보내면 위험한 결과 | `evidence=SUMMARY` 또는 `evidence=REDACTED` |
| audit trail에 구조화 결과가 필요한 경우 | `evidence=STRUCTURED` |

`@agent_tool` signature는 schema의 정본입니다. Parameter와 return type은 annotation해야 합니다. Dataclass, primitive, enum, list, tuple, mapping, optional/union, `Annotated` 기반 sensitive metadata가 지원됩니다. `*args`, `**kwargs`, positional-only parameter, JSON schema로 표현할 수 없는 임의 object는 definition 단계에서 실패합니다.

## 5. Tool catalog를 model에게 전달하기

`@Agent` metadata에는 discovered tool catalog가 들어 있습니다.

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

Model adapter가 `ModelStreamEventKind.TOOL_CALL_CANDIDATE`를 emit하면 agent는 다음 순서로 처리합니다.

1.  `call.name`으로 `AgentToolCatalog`에서 descriptor를 찾습니다.
2.  `plan_agent_tool_approval()`로 approval이 필요한지 판단합니다.
3.  필요하면 `AgentYieldKind.APPROVAL`을 yield하고 decision signal을 기다립니다.
4.  승인되었거나 approval이 필요 없으면 `descriptor.bind_invocation(call.arguments)`로 argument를 검증합니다.
5.  Python method를 호출합니다.
6.  result를 `AgentYieldKind.TOOL`이나 evidence로 남깁니다.

핵심 코드 shape는 다음과 같습니다.

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

## 6. Approval, signal, cancel 이해하기

Approval은 "모든 tool 앞에서 무조건 묻기"가 아닙니다. Tool metadata에서 risk를 계산하고, side effect가 있는 boundary에서만 approval request를 materialize합니다.

Approval이 필요한 경우 agent는 `AgentYieldKind.APPROVAL`을 내보냅니다. Inbound adapter는 이 event를 UI로 보여주고, 사용자의 결정을 `AgentSignal`로 append합니다.

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

Signal은 실행 중 agent에게 들어오는 외부 입력입니다.

| signal kind | 의미 |
| --- | --- |
| `USER_MESSAGE` | 실행 중 사용자가 추가 지시를 보냄 |
| `APPROVAL_DECISION` | approval request에 대한 approve/reject/modify/defer/cancel 결정 |
| `CANCEL` | 실행 취소 요청 |
| `RESUME` | 중단된 실행 재개 요청 |
| `STEERING_INSTRUCTION` | 실행 방향을 바꾸는 운영 지시 |
| `EXTERNAL_EVENT` | 외부 시스템에서 들어온 event |
| `SCHEDULER_WAKE_UP` | scheduler가 agent를 깨움 |

Durable repository를 쓰는 경우 orchestration은 safe boundary에서 `consume_pending_agent_signals()`를 호출합니다. 이 helper는 pending queue를 append order로 읽고, 현재 agent가 받아들일 수 있는 prefix만 consumed 처리합니다. 앞선 signal을 건너뛰고 뒤 signal을 먼저 처리하지 않습니다.

Cancel은 바로 `FAILED`나 `CANCELLED`로 덮어쓰는 단순 flag가 아닙니다. 일반적인 흐름은 `begin_agent_cancellation()`으로 state를 `CANCELLING`으로 만들고, model stream/tool/delegate cleanup hook을 실행하고, cleanup 결과에 따라 `complete_agent_cancellation()`이 `CANCELLED` 또는 cleanup failure로 끝냅니다.

## 7. Durable 실행과 repository

짧은 agent는 repository 없이도 동작할 수 있습니다. 하지만 다음 중 하나를 쓰면 durable path입니다.

- `AgentExecutionSpec(recovery=RecoveryStrategy.ACTION_BOUNDARY)`
- `AgentExecutionSpec(accepted_signals=(...))`

Durable path에서는 bootstrap이 다음 세 repository port를 요구합니다.

| repository | 저장하는 것 |
| --- | --- |
| `IAgentStateRepository` | `AgentState`: 현재 status, transition, current activity, input ref |
| `IAgentSignalRepository` | `AgentSignal`: user message, approval decision, cancel 같은 inbound queue |
| `IAgentEvidenceRepository` | `AgentEvidence`: tool/model/context 판단 근거와 action-boundary checkpoint |

운영에서는 `spakky-sqlalchemy[agent]` contribution을 사용합니다.

```bash
pip install "spakky-sqlalchemy[agent]"
```

이 contribution은 `spakky.contributions.spakky.agent` entry point로 SQLAlchemy repository와 table을 등록합니다. 운영용 in-memory fallback은 없습니다. Repository가 없는데 durable path를 선언하면 bootstrap에서 fail-fast해야 합니다.

`AgentExecutionSpec` 예시는 다음과 같습니다.

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
| --- | --- |
| 이미 완료된 action boundary | 완료된 action을 다시 실행하지 않고 skip |
| idempotent action이 incomplete | retry 가능 |
| non-idempotent/unknown action이 incomplete | 사람 확인 필요 |
| approval wait 중 재시작 | approval decision을 기다림 |

Evidence는 append-only입니다. Tool result를 수정하거나 삭제해서 history를 고치지 않고, redaction/correction/context digest 갱신도 새 evidence를 append하는 방식으로 표현합니다.

## 8. FastAPI, WebSocket, SSE, CLI로 노출하기

Agent 전용 inbound package는 필요하지 않습니다. 기존 `spakky-fastapi`나 `spakky-typer` controller에서 agent를 resolve하고 stream을 변환합니다.

### WebSocket

WebSocket adapter의 핵심은 다음과 같습니다.

```python
@websocket("/agents/code/ws")
async def code_socket(self, websocket: WebSocket) -> None:
    command = await websocket.receive_json()
    agent = self._container.get(CodeAssistant)
    async for item in agent.execute(command):
        await websocket.send_json(agent_yield_to_event(item))
```

실제 예제인 `core/spakky-agent/examples/inbound_adapter_examples.py`는 다음 일을 합니다.

- `container.get(CodeAssistant)`로 agent resolve
- `AgentYield`를 `{"kind": ..., "payload": ...}` JSON event로 변환
- `APPROVAL` event가 나오면 WebSocket 또는 stdin에서 decision JSON을 읽음
- decision JSON을 `AgentSignalKind.APPROVAL_DECISION`으로 변환해 repository에 append
- CLI에서는 `TOKEN` payload만 stdout에 이어 쓰고 나머지는 line event로 출력

### SSE

SSE는 단방향 server-to-client stream입니다. 사용자의 새 메시지나 approval decision을 같은 연결로 받을 수 없으므로, SSE endpoint와 별도의 POST endpoint를 함께 둡니다.

- `POST /agents/code/sse`: 실행을 시작하고 `AgentYield`를 SSE frame으로 stream합니다.
- `POST /agents/code/signals`: approval decision, cancel, user message를 `IAgentSignalRepository`에 append합니다.

`spakky-fastapi`의 `@post` decorator는 FastAPI `response_class`를 받을 수 있고, controller method가 반환한 `StreamingResponse`를 그대로 반환합니다. 따라서 SSE endpoint는 다음처럼 작성합니다.

```python
from collections.abc import AsyncIterator, Mapping
import json

from examples.code_assistant_demo import CodeAssistant
from examples.inbound_adapter_examples import (
    agent_signal_from_json,
    agent_yield_to_event,
    code_assistant_command_from_json,
)
from fastapi.responses import StreamingResponse
from spakky.agent import IAgentSignalRepository, JsonValue
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.plugins.fastapi.routes import post
from spakky.plugins.fastapi.stereotypes.api_controller import ApiController


@ApiController("/agents")
class AgentSseController(IContainerAware):
    _container: IContainer

    def set_container(self, container: IContainer) -> None:
        self._container = container

    @post("/code/sse", response_class=StreamingResponse)
    async def code_sse(self, payload: dict[str, object]) -> StreamingResponse:
        command = code_assistant_command_from_json(payload)

        async def stream() -> AsyncIterator[str]:
            agent = self._container.get(CodeAssistant)
            async for item in agent.execute(command):
                yield _sse_data(agent_yield_to_event(item))

        return StreamingResponse(stream(), media_type="text/event-stream")

    @post("/code/signals")
    async def append_signal(self, payload: dict[str, object]) -> dict[str, str]:
        state_id = _required_text(payload, "state_id")
        signal_payload = payload.get("signal")
        signals = self._container.get(IAgentSignalRepository)
        signals.append(agent_signal_from_json(state_id, signal_payload))
        return {"status": "accepted"}


def _sse_data(event: Mapping[str, JsonValue]) -> str:
    body = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"data: {body}\n\n"


def _required_text(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if isinstance(value, str) and value.strip():
        return value
    raise ValueError(f"{name} must be non-empty text")
```

위 예제는 Spakky 내부 event shape를 SSE로 내보냅니다.

```text
data: {"kind":"token","payload":{"text":"hello","metadata":{}}}

data: {"kind":"final","payload":{"output":...,"metadata":{}}}

```

이 shape는 Spakky-native stream이지 AG-UI wire format이 아닙니다. CopilotKit이나 AG-UI client에 직접 연결하려면 다음 절의 AG-UI adapter shape로 변환해야 합니다.

## 9. AG-UI와 CopilotKit 호환성

AG-UI는 `AgentYield`와 다른 wire protocol입니다. 공식 AG-UI HTTP agent는 POST body로 `threadId`, `runId`, `messages`, `state`, `tools`, `context`, `forwardedProps`를 받고, 응답은 `text/event-stream`으로 `data: {"type": ...}` frame을 stream합니다. 대표 event type은 `RUN_STARTED`, `TEXT_MESSAGE_START`, `TEXT_MESSAGE_CONTENT`, `TEXT_MESSAGE_END`, `TOOL_CALL_START`, `TOOL_CALL_ARGS`, `TOOL_CALL_END`, `TOOL_CALL_RESULT`, `STATE_SNAPSHOT`, `STATE_DELTA`, `CUSTOM`, `RUN_FINISHED`, `RUN_ERROR`입니다.

따라서 현재 Spakky 상태를 정확히 말하면 다음과 같습니다.

- `spakky-agent`는 AG-UI와 개념적으로 맞는 stream/event building block을 제공합니다.
- `AgentYield` 자체는 AG-UI event가 아닙니다.
- 현재 repository에는 built-in `spakky-agent-agui` adapter나 AG-UI event class가 없습니다.
- CopilotKit은 AG-UI `HttpAgent`로 Spakky backend에 붙을 수 있지만, Spakky 쪽에 AG-UI HTTP/SSE adapter endpoint를 구현해야 합니다.

### AgentYield to AG-UI mapping

권장 mapping은 다음과 같습니다.

| Spakky `AgentYieldKind` | AG-UI event | 설명 |
| --- | --- | --- |
| stream 시작 전 | `RUN_STARTED` | `threadId`와 `runId`는 AG-UI request에서 받은 값을 그대로 사용합니다. |
| 첫 `TOKEN` 전 | `TEXT_MESSAGE_START` | assistant message id를 생성합니다. |
| `TOKEN` | `TEXT_MESSAGE_CONTENT` | `Token.text`를 `delta`로 보냅니다. |
| `PROGRESS` | `CUSTOM` | Spakky progress는 AG-UI step lifecycle과 1:1이 아니므로 `CUSTOM`이 안전합니다. |
| `TOOL` call args | `TOOL_CALL_START` + `TOOL_CALL_ARGS` + `TOOL_CALL_END` | `Tool.arguments`를 JSON string delta로 보냅니다. |
| `TOOL` result | `TOOL_CALL_RESULT` | `Tool.result`를 JSON string 또는 text content로 보냅니다. |
| `APPROVAL` | `CUSTOM` 또는 `STATE_DELTA` | AG-UI core에는 Spakky approval 전용 event가 없으므로 frontend 약속이 필요합니다. |
| `EVIDENCE` | `CUSTOM` 또는 `STATE_DELTA` | UI에 audit reference를 보여주려면 custom event가 적합합니다. |
| `FINAL` | `TEXT_MESSAGE_END` + `RUN_FINISHED` | token message가 열려 있으면 먼저 닫습니다. |
| `ERROR` | `RUN_ERROR` | `Error.message`를 AG-UI error message로 보냅니다. |
| `CANCEL` | `CUSTOM` + `RUN_FINISHED` | 취소를 error로 볼지 정상 종료로 볼지는 product policy로 정합니다. |

AG-UI endpoint 예시는 다음과 같습니다. 이 코드는 Spakky `AgentYield` stream을 AG-UI SSE frame으로 바꾸는 adapter입니다.

```python
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
import json
from uuid import uuid4

from examples.code_assistant_demo import CodeAssistant, CodeAssistantCommand
from fastapi.responses import StreamingResponse
from spakky.agent import AgentYieldKind, Error, Final, Progress, Token, Tool
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.plugins.fastapi.routes import post
from spakky.plugins.fastapi.stereotypes.api_controller import ApiController


@dataclass(frozen=True, slots=True)
class AgUiRunInput:
    thread_id: str
    run_id: str
    instruction: str
    state: dict[str, object] = field(default_factory=dict)


@ApiController("/agents")
class AgUiAgentController(IContainerAware):
    _container: IContainer

    def set_container(self, container: IContainer) -> None:
        self._container = container

    @post("/code/ag-ui", response_class=StreamingResponse)
    async def run_code_agent(self, payload: dict[str, object]) -> StreamingResponse:
        input_data = _ag_ui_input(payload)

        async def stream() -> AsyncIterator[str]:
            async for frame in self._run_as_ag_ui(input_data):
                yield frame

        return StreamingResponse(stream(), media_type="text/event-stream")

    async def _run_as_ag_ui(self, input_data: AgUiRunInput) -> AsyncIterator[str]:
        message_id = f"msg_{uuid4().hex}"
        message_open = False
        yield _ag_ui_sse({"type": "RUN_STARTED", "threadId": input_data.thread_id, "runId": input_data.run_id})

        agent = self._container.get(CodeAssistant)
        command = CodeAssistantCommand(
            state_id=input_data.run_id,
            instruction=input_data.instruction,
        )
        async for item in agent.execute(command):
            if item.kind is AgentYieldKind.TOKEN and isinstance(item.payload, Token):
                if not message_open:
                    yield _ag_ui_sse({"type": "TEXT_MESSAGE_START", "messageId": message_id, "role": "assistant"})
                    message_open = True
                yield _ag_ui_sse({"type": "TEXT_MESSAGE_CONTENT", "messageId": message_id, "delta": item.payload.text})
            elif item.kind is AgentYieldKind.PROGRESS and isinstance(item.payload, Progress):
                yield _ag_ui_sse({"type": "CUSTOM", "name": "spakky.progress", "value": {"message": item.payload.message, "currentStep": item.payload.current_step}})
            elif item.kind is AgentYieldKind.TOOL and isinstance(item.payload, Tool):
                yield _ag_ui_sse({"type": "TOOL_CALL_RESULT", "toolCallId": item.payload.call_id or item.payload.name, "content": json.dumps(item.payload.result, ensure_ascii=False)})
            elif item.kind is AgentYieldKind.FINAL and isinstance(item.payload, Final):
                if message_open:
                    yield _ag_ui_sse({"type": "TEXT_MESSAGE_END", "messageId": message_id})
                    message_open = False
                yield _ag_ui_sse({"type": "RUN_FINISHED", "threadId": input_data.thread_id, "runId": input_data.run_id})
            elif item.kind is AgentYieldKind.ERROR and isinstance(item.payload, Error):
                yield _ag_ui_sse({"type": "RUN_ERROR", "message": item.payload.message})


def _ag_ui_sse(event: Mapping[str, object]) -> str:
    body = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"data: {body}\n\n"
```

`_ag_ui_input()`은 AG-UI request body를 Spakky command로 좁히는 application adapter입니다. 일반적으로 마지막 user message를 instruction으로 사용하고, `runId`를 durable `state_id`로 사용합니다.

```python
def _ag_ui_input(payload: Mapping[str, object]) -> AgUiRunInput:
    messages = payload.get("messages")
    instruction = ""
    if isinstance(messages, list):
        for message in reversed(messages):
            if isinstance(message, Mapping) and message.get("role") == "user":
                content = message.get("content")
                if isinstance(content, str):
                    instruction = content
                    break
    return AgUiRunInput(
        thread_id=_required_text(payload, "threadId"),
        run_id=_required_text(payload, "runId"),
        instruction=instruction,
        state=_object_payload(payload.get("state")),
    )


def _object_payload(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _required_text(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if isinstance(value, str) and value.strip():
        return value
    raise ValueError(f"{name} must be non-empty text")
```

AG-UI request의 `tools`는 frontend/runtime이 agent에게 알려주는 tool schema입니다. 이것이 Spakky `@agent_tool` catalog에 자동으로 합쳐지지는 않습니다. 외부 AG-UI tools를 Spakky model request에 전달하려면 adapter가 AG-UI tool schema를 `ModelToolSpec`으로 변환해야 합니다. 반대로 Spakky backend tools를 model에 노출하려면 앞 절처럼 `Agent.get(MyAgent).tool_catalog`를 `ToolCallingSpec`으로 변환합니다.

### CopilotKit 연결

CopilotKit은 AG-UI `HttpAgent`를 통해 custom agent endpoint에 붙을 수 있습니다. Spakky backend가 위와 같은 AG-UI HTTP/SSE endpoint를 제공하면 CopilotKit runtime에서는 그 URL을 agent로 등록합니다.

```ts
import {
  CopilotRuntime,
  ExperimentalEmptyAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import { HttpAgent } from "@ag-ui/client";
import { NextRequest } from "next/server";

const serviceAdapter = new ExperimentalEmptyAdapter();

const runtime = new CopilotRuntime({
  agents: {
    code: new HttpAgent({ url: "http://localhost:8000/agents/code/ag-ui" }),
  },
});

export const POST = async (req: NextRequest) => {
  const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
    runtime,
    serviceAdapter,
    endpoint: "/api/copilotkit",
  });
  return handleRequest(req);
};
```

정리하면 CopilotKit으로 붙일 수는 있습니다. 단, 조건은 Spakky endpoint가 CopilotKit `HttpAgent`가 기대하는 AG-UI request/response를 구현해야 한다는 것입니다. `AgentYield`를 그대로 SSE로 흘리는 Spakky-native endpoint는 CopilotKit용 endpoint가 아닙니다.

## 10. 테스트 전략

Agent 테스트는 실제 LLM에 의존하지 않는 것이 좋습니다.

| 테스트 대상 | 권장 double |
| --- | --- |
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

## 전체 개발 순서

처음부터 durable CodeAssistant를 만들려고 하면 어렵습니다. 이 순서로 쌓는 것이 안전합니다.

1.  `@Agent` class와 `execute()`만 만든다.
2.  `AgentYieldKind.FINAL`만 yield해서 container resolve와 invocation을 확인한다.
3.  `IAgentModel`을 constructor로 받고 token stream을 `AgentYieldKind.TOKEN`으로 변환한다.
4.  read-only `@agent_tool` 하나를 추가하고 tool catalog schema를 확인한다.
5.  model request에 `ToolCallingSpec`을 넣고 tool-call candidate를 처리한다.
6.  write/network/destructive tool을 추가하고 approval event를 처리한다.
7.  `accepted_signals`나 `RecoveryStrategy.ACTION_BOUNDARY`를 선언한다.
8.  `spakky-sqlalchemy[agent]` contribution 또는 repository provider를 등록한다.
9.  FastAPI/WebSocket/SSE adapter에서 `AgentYield`를 transport event로 변환한다.
10. AG-UI/CopilotKit이 필요하면 `AgentYield`를 AG-UI event로 변환하는 HTTP/SSE adapter를 추가한다.
11. scripted model과 repository double로 token, tool, approval, cancel, resume 테스트를 작성한다.

## Production checklist

- `@Agent.execute()` input과 return/yield type이 모두 annotate되어 있다.
- Agent가 provider SDK, DB client, HTTP framework를 직접 import하지 않고 port/interface에 의존한다.
- Model backend는 `IAgentModel` adapter 뒤에 있다.
- 모든 model-callable capability는 `@agent_tool`로 선언되어 schema, risk, idempotency, evidence metadata가 있다.
- Write/network/destructive tool은 approval path가 있다.
- Durable path를 쓰면 state/signal/evidence repository contribution이 등록되어 있다.
- Inbound adapter는 `AgentYieldKind.APPROVAL`을 사용자 decision signal로 연결한다.
- CopilotKit 연동 endpoint는 Spakky-native `AgentYield` JSON이 아니라 AG-UI `type` event stream을 반환한다.
- Cancel은 cancellation lifecycle로 처리하고 즉시 terminal state로 덮지 않는다.
- Evidence는 append-only로 남긴다.
- 테스트는 실제 model server 없이 scripted stream으로 주요 branch를 검증한다.

## 더 볼 곳

- [CodeAssistant 에이전트 예제](agent-code-assistant.md): workspace/shell/git tool, approval, evidence, cancel/resume을 한 execution으로 연결한 runnable demo입니다.
- [spakky-agent API Reference](../api/core/spakky-agent.md): public class와 helper의 상세 signature를 확인합니다.
- [spakky-vllm API Reference](../api/plugins/spakky-vllm.md): OpenAI-compatible vLLM model adapter를 확인합니다.
- [spakky-sqlalchemy API Reference](../api/plugins/spakky-sqlalchemy.md): durable agent repository contribution을 확인합니다.
