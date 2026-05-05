# ADR-0009: Agentic Hexagonal Architecture

- **상태**: Accepted
- **날짜**: 2026-05-04
- **갱신**: 2026-05-06
- **대체**: 해당 없음
- **선행 완료**: [ADR-0010 Feature Contribution Policy](0010-feature-contribution-policy.md)

## 맥락 (Context)

Spakky Framework에 LLM 기반 agentic application 지원을 추가하는 방향을 논의했다. 초기 구상은 LangGraph, Pydantic AI, vLLM 같은 기존 agent/LLM framework를 Spakky plugin으로 감싸는 방식이었다. 그러나 논의 결과 `spakky-agent`는 외부 agent framework의 adapter가 아니라, Spakky의 DDD/hexagonal architecture 위에서 agentic business workflow를 작성하기 위한 native framework 기능이어야 한다.

Agent는 별도 애플리케이션 계층이 아니다. Spakky에서 Agent는 `@UseCase`와 치환 가능한 동격의 `@Pod` stereotype이다. 차이는 deterministic branching 대신 model-mediated decision을 사용해 orchestration한다는 점이다.

즉 `@Agent`는 다음 성격을 가진다.

- inbound adapter에서 호출되는 application component다.
- outbound port를 DI로 주입받아 사용한다.
- LLM/model 호출도 outbound infrastructure 호출이다.
- tool 호출도 outbound capability/port 호출이다.
- long-running, streaming, pause/resume, cancellation, HITL, subtask delegation을 지원할 수 있다.
- 실행 흐름은 비결정적일 수 있지만 여전히 비즈니스 로직이다.

이 ADR은 구현 가능한 단일 마일스톤 스펙이다. 마일스톤은 쪼개지 않는다. 하나의 완전한 마일스톤은 모든 public contract와 실제 실행 가능한 유즈케이스를 포함해야 한다.

## 결정 동인 (Decision Drivers)

- Agent는 LLM wrapper가 아니라 `@UseCase`와 동격인 application workflow component여야 한다.
- Core는 저수준 인프라 구현을 포함하지 않지만, 사용자 DX 표면, execution contract, orchestration building block, typed metadata, lifecycle semantics는 소유해야 한다.
- Core feature는 plugin을 통한 간접 설치를 전제로 한다. Production in-memory persistence 구현은 제공하지 않는다.
- Persistence는 optional nice-to-have가 아니라 pause/resume/recovery/evidence를 위한 필수 계약이다.
- ADR-0010 contribution system을 사용해 `spakky-sqlalchemy`가 agent persistence 구현을 기여한다.
- Agent 전용 inbound adapter package를 만들지 않는다. 기존 FastAPI/Typer/gRPC building block으로 inbound adapter를 작성할 수 있어야 한다.
- 첫 model implementation은 오픈소스, 무료, 로컬 실행 가능한 vLLM을 우선한다.
- Pydantic AI/LangGraph/LiteLLM은 첫 구현의 정본이 아니다. 향후 bridge/gateway 후보일 수 있지만 `spakky-agent`의 core identity를 대체하지 않는다.
- Streaming token은 client-side로 실시간 서빙될 수 있어야 한다.
- 민감정보 보호는 prompt instruction에 의존하지 않고 deterministic guard와 typed metadata로 처리한다.

## 결정 (Decision)

ADR-0009 마일스톤은 다음을 하나의 완성 단위로 구현한다.

| 패키지 | 역할 |
|------|------|
| `core/spakky-agent` | `@Agent` stereotype, execution spec, state/signal/evidence contract, `AgentYield`, model/tool/schema/safety/recovery building block |
| `plugins/spakky-vllm` | 첫 공식 `IAgentModel` 구현. 로컬 vLLM OpenAI-compatible HTTP server에 연결 |
| `plugins/spakky-sqlalchemy` contribution | `spakky-agent`의 `AgentStateRepository`, `AgentSignalRepository`, `AgentEvidenceRepository` 구현 기여 |

명시적으로 만들지 않는다.

| 패키지 | 결정 |
|------|------|
| `core/spakky-llm` | 만들지 않는다. LLM 호출 계약은 `spakky-agent`의 `IAgentModel`에 포함한다. |
| `plugins/spakky-pydantic-ai` | 첫 마일스톤에 포함하지 않는다. Spakky-native framework가 정본이다. |
| `plugins/spakky-langgraph` | 첫 마일스톤에 포함하지 않는다. 향후 graph bridge 후보로 남긴다. |
| `plugins/spakky-litellm` | 첫 마일스톤에 포함하지 않는다. 향후 gateway/routing/fallback adapter 후보로 남긴다. |
| `plugins/spakky-agent-fastapi` | 만들지 않는다. 기존 `spakky-fastapi` building block을 사용한다. |
| `plugins/spakky-agent-typer` | 만들지 않는다. 기존 `spakky-typer` building block을 사용한다. |
| `plugins/spakky-agent-mcp` | 만들지 않는다. 외부 tool/protocol descriptor는 향후 adapter가 `AgentTool`로 normalize한다. |
| `plugins/spakky-agent-a2a` | 만들지 않는다. A2A server adapter는 첫 마일스톤 범위 밖이다. |
| `plugins/spakky-agent-sqlalchemy` | 만들지 않는다. ADR-0010 contribution으로 `plugins/spakky-sqlalchemy`에 둔다. |

## 마일스톤 성공 그림

이 마일스톤이 성공하면 Framework 사용자는 Claude Code 같은 coding assistant를 "프레임워크가 제공하는 완제품"으로 받는 것이 아니라, 일반 UseCase를 만들듯 `@Agent` application component로 작성할 수 있다.

전체 조립은 다음처럼 보인다.

```text
CLI / FastAPI / WebSocket inbound adapter
  -> @Agent CodeAssistant.execute(CodeTask)
      -> IAgentModel via plugins/spakky-vllm
      -> @agent_tool workspace/search/read/write/bash/git capabilities
      -> AgentState / AgentSignal / AgentEvidence repositories
      -> AgentEvent via spakky-event/outbox
      -> AgentYield stream
  -> client
```

프레임워크가 제공하는 것은 coding assistant 자체가 아니라 다음 building block이다.

- `@Agent`: coding assistant를 UseCase와 같은 application component로 선언한다.
- `IAgentModel`: vLLM 같은 model backend를 outbound adapter로 호출한다.
- `@agent_tool`: workspace, file, shell, git, search 같은 기능을 typed tool로 노출한다.
- `AgentYield`: 생성 중인 텍스트, 중간 메시지, evidence, approval, final output을 caller에게 streaming한다.
- `AgentSignal`: 실행 중 사용자 지시, 승인, 취소를 agent state에 전달한다.
- `AgentStateRepository`: long-running 실행 상태를 노출하고 recovery 기준으로 사용한다.
- `AgentEvidenceRepository`: tool/model/context 판단 근거와 context manifest/digest를 저장한다.

따라서 Claude Code-like assistant는 다음과 같은 application code가 된다.

```python
@Pod
class WorkspaceTools:
    @agent_tool(
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        evidence=EvidenceCapture.structured(),
    )
    async def read_file(self, path: WorkspacePath) -> FileContent:
        ...

    @agent_tool(
        effects=ToolEffects.write_state(),
        idempotency=Idempotency.NON_IDEMPOTENT,
        evidence=EvidenceCapture.reference_only(),
    )
    async def write_file(self, path: WorkspacePath, content: str) -> FilePatch:
        ...


@Pod
class ShellTools:
    @agent_tool(
        effects=ToolEffects.external_side_effect(),
        idempotency=Idempotency.UNKNOWN,
        evidence=EvidenceCapture.summary(),
    )
    async def run(self, command: ShellCommand) -> ShellResult:
        ...


@Agent(
    spec=AgentExecutionSpec(
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
        accepted_signals=[
            AgentSignalKind.USER_MESSAGE,
            AgentSignalKind.APPROVAL_DECISION,
            AgentSignalKind.CANCEL,
        ],
        streaming_exposure_mode=StreamingExposureMode.BALANCED,
    )
)
class CodeAssistant:
    def __init__(
        self,
        model: IAgentModel,
        workspace: WorkspaceTools,
        shell: ShellTools,
        git: GitTools,
    ):
        self.model = model
        self.workspace = workspace
        self.shell = shell
        self.git = git

    async def execute(
        self,
        task: CodeTask,
    ) -> AsyncGenerator[AgentYield[CodeTaskResult], None]:
        yield AgentYield(
            kind=AgentYieldKind.PROGRESS,
            payload=Progress("Inspecting workspace"),
        )

        tools = [
            self.workspace.read_file,
            self.workspace.write_file,
            self.shell.run,
            self.git.diff,
        ]

        while True:
            async for event in self.model.stream(
                ModelRequest(
                    messages=[
                        ModelMessage.system(task.instructions),
                        ModelMessage.evidence(task.context_refs),
                    ],
                    tools=ToolCallingSpec.from_tools(tools),
                    output=StructuredOutputSpec.from_type(CodeAssistantDecision),
                )
            ):
                if event.is_text_delta:
                    yield AgentYield(
                        kind=AgentYieldKind.TOKEN,
                        payload=Token(event.text),
                    )

                if event.is_tool_call:
                    result = await event.invoke_tool()
                    yield AgentYield(
                        kind=AgentYieldKind.TOOL,
                        payload=Tool(event.name, call_id=event.call_id, result=result),
                    )

                if event.is_approval_required:
                    yield AgentYield(
                        kind=AgentYieldKind.APPROVAL,
                        payload=Approval.from_request(event.request),
                    )

                if event.is_final:
                    yield Final(event.output)
                    return
```

Inbound adapter는 이 generator를 그대로 소비한다.

```python
@app.websocket("/agents/code")
async def code_agent_socket(ws: WebSocket, command: CodeTask):
    agent = container.get(CodeAssistant)

    async for item in agent.execute(command):
        await ws.send_json(AgentYieldJsonEncoder.encode(item))
```

사용자가 실행 중 추가 지시를 보내거나 승인을 결정하면 inbound adapter는 `AgentSignalRepository`에 signal을 append한다. Scheduler/application orchestration은 safe boundary에서 signal을 반영한다. 이때 agent business logic은 여전히 `CodeAssistant.execute()`이고, persistence, signal, evidence, recovery는 framework building block이 보조한다.

완성된 마일스톤의 데모는 다음을 보여야 한다.

1. 개발자가 `@Agent CodeAssistant`와 `@agent_tool` workspace/shell/git tool을 작성한다.
2. FastAPI 또는 Typer inbound adapter가 `CodeAssistant.execute()`를 호출한다.
3. vLLM local server가 model decision과 token stream을 제공한다.
4. `Token` yield가 client로 실시간 전달된다.
5. Model이 file read/search/bash/write tool call을 선택하고 typed schema로 arguments를 만든다.
6. Write/bash 같은 unsafe action은 approval signal을 요구할 수 있다.
7. 사용자는 실행 중 추가 지시, 승인, 취소를 signal로 보낸다.
8. Process restart 후 incomplete action boundary에서 resume한다.
9. Evidence와 context manifest/digest가 SQLAlchemy contribution으로 저장된다.
10. Secret/sensitive field는 LLM-facing context와 stream에서 deterministic guard를 통과한다.

## 핵심 모델

### `@Agent`

`@Agent`는 `@UseCase`와 동격인 `@Pod` stereotype이다.

```python
@Agent(
    spec=AgentExecutionSpec(
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
        accepted_signals=[
            AgentSignalKind.USER_MESSAGE,
            AgentSignalKind.APPROVAL_DECISION,
            AgentSignalKind.CANCEL,
        ],
        streaming_exposure_mode=StreamingExposureMode.BALANCED,
    )
)
class ResolveSupportTicket:
    def __init__(self, model: IAgentModel, docs: DocsTools):
        self.model = model
        self.docs = docs

    async def execute(
        self,
        command: ResolveSupportTicketCommand,
    ) -> AsyncGenerator[AgentYield[SupportAnswer], None]:
        ...
```

`execute()`는 agent의 business entrypoint다. `AgentRunContext` 같은 runtime context 객체를 인자로 노출하지 않는다. 모델, tool, repository, external service는 일반 Spakky component처럼 DI로 주입한다.

`@Agent.execute()`는 직접 호출 가능하다. 호출자는 `@UseCase.execute()`를 호출하듯 input DTO를 넘기고 output 또는 `AgentYield` stream을 받는다. Scheduler, repository, contribution, inbound adapter는 이 같은 business operation을 long-running/recoverable execution으로 운영하기 위한 주변 구성요소다.

### UseCase-Shaped Agent Authoring

개발자가 Agent를 작성하는 감각은 UseCase 작성과 같아야 한다.

```python
@UseCase
class ResolveSupportTicket:
    def __init__(self, docs: DocsPort):
        self.docs = docs

    async def execute(self, command: ResolveSupportTicketCommand) -> SupportAnswer:
        docs = await self.docs.search(command.question)
        return SupportAnswer.from_docs(docs)
```

동일한 workflow가 model-mediated orchestration을 필요로 하면 `@Agent`로 작성한다.

```python
@Agent
class ResolveSupportTicket:
    def __init__(
        self,
        model: IAgentModel,
        docs: DocsTools,
        tickets: TicketPort,
    ):
        self.model = model
        self.docs = docs
        self.tickets = tickets

    async def execute(
        self,
        command: ResolveSupportTicketCommand,
    ) -> AsyncGenerator[AgentYield[SupportAnswer], None]:
        yield AgentYield(
            kind=AgentYieldKind.PROGRESS,
            payload=Progress("Searching support knowledge base"),
        )

        docs = await self.docs.search_docs(command.question, limit=5)
        yield AgentYield(kind=AgentYieldKind.EVIDENCE, payload=Evidence(docs))

        async for event in self.model.stream(
            ModelRequest(
                messages=[
                    ModelMessage.user(command.question),
                    ModelMessage.evidence(docs),
                ],
                output=StructuredOutputSpec.from_type(SupportAnswer),
            )
        ):
            if event.is_text_delta:
                yield AgentYield(kind=AgentYieldKind.TOKEN, payload=Token(event.text))

        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(SupportAnswer(...), metadata={}),
        )
```

이 예시에서 외부 인프라와의 상호작용은 모두 생성자 DI로 정의된다.

- `IAgentModel`: LLM outbound interface
- `DocsTools`: `@agent_tool`로 노출 가능한 application capability
- `TicketPort`: 일반 outbound port

`@Agent` decorator는 이 의존성을 다시 선언하지 않는다. `@Agent`가 제공하는 것은 이 class가 agentic workflow component라는 stereotype, `execute()` streaming contract, schema/metadata 검증, state/signal/evidence/recovery integration point다.

### `AgentExecutionSpec`

`AgentExecutionSpec`은 인프라 의존성을 선언하는 객체가 아니다. 외부 인프라 의존성은 생성자 DI와 contribution system이 정의한다.

`AgentExecutionSpec`은 `execute()` signature와 DI graph만으로 추론하기 어려운 실행 의미를 보조적으로 선언한다.

- accepted signal kinds
- recovery strategy
- `streaming_exposure_mode`
- timeout/deadline 설정
- output guard profile
- delegation/recovery constraints

다음은 `AgentExecutionSpec`의 public boolean flag가 아니다.

- `durable`
- `interactive`
- `streaming`
- `resumable`

이 속성들은 독립 옵션이 아니라 다른 계약에서 파생된다.

- Streaming은 `execute()` 반환형이 `Generator[AgentYield[T], None, None]` 또는 `AsyncGenerator[AgentYield[T], None]`인지로 판정한다.
- Interaction은 `accepted_signals`와 `AgentSignalRepository` 활성화 여부로 판정한다.
- Durability는 `AgentStateRepository`, `AgentSignalRepository`, `AgentEvidenceRepository` contribution이 필요한 실행 경로에서 요구된다.
- Resumability는 `recovery` strategy가 action-boundary recovery를 요구할 때 파생된다.

Bootstrap은 `@Agent` metadata, `execute()` signature, DI graph, contribution registry를 함께 검증한다. 필요한 repository/model/tool contribution이 없으면 startup fail한다. Silent fallback은 허용하지 않는다.

### `AgentState`

`AgentState`는 long-running agent process의 materialized state다.

- id
- agent type
- status
- current phase/activity summary
- input/output reference
- pending signal count
- last event cursor
- recovery marker
- timestamps

`AgentState`는 조회와 orchestration을 위한 materialized process state다. Append-only log를 매번 full replay하지 않도록 state를 유지하지만, conformance check는 state/log/evidence divergence를 감지할 수 있어야 한다.

Top-level status는 외부 lifecycle만 표현한다.

- `CREATED`
- `ACTIVE`
- `INTERRUPTED`
- `CANCELLING`
- `COMPLETED`
- `FAILED`
- `CANCELLED`

`WAITING_APPROVAL`은 top-level status가 아니다. `INTERRUPTED(reason=APPROVAL_REQUIRED)`로 표현한다. `TIMED_OUT`도 top-level status가 아니라 `FAILED(reason=TIMEOUT)`로 표현한다.

계획, 실행, 평가, 위임 같은 인지적 활동은 lifecycle status가 아니라 병행 가능한 activity/event/evidence로 표현한다.

### `AgentSignal`

`AgentSignal`은 실행 중인 `AgentState`에 들어오는 inbound stimulus다.

- user message
- approval decision
- cancel
- pause/resume
- steering instruction
- external event
- scheduler wake-up

`AgentSignal`은 이미 발생한 사실인 `AgentEvent`와 다르다. Signal은 agent를 진행시키는 외부 입력이고, event는 agent 실행이 남긴 사실이다.

### `AgentYield`

`AgentYield`는 `@Agent.execute()`가 caller/inbound adapter에 streaming으로 돌려주는 public item이다.

Canonical handler return type은 다음이다.

```python
Generator[AgentYield[OutputT], None, None]
AsyncGenerator[AgentYield[OutputT], None]
```

최종 결과는 `Final[OutputT]` yield로 표현한다. Python async generator는 return value를 가질 수 없고, sync generator의 `StopIteration.value`도 public output contract로 사용하지 않는다.

Non-generator `execute()` 반환형은 UseCase와 같은 직접 결과 계약이다. 직접 결과는 caller가 await/call 결과를 받는 방식이고, inbound adapter가 진행 상황을 stream으로 노출해야 할 때는 `AgentYield` generator 계약을 사용한다.

Public yield vocabulary는 작게 유지한다.

- `Token`
- `Progress`
- `Tool`
- `Evidence`
- `Approval`
- `Final[OutputT]`
- `Error`
- `Cancel`

Inbound adapter는 `AgentYield`를 직접 소비해 SSE, WebSocket, CLI stdout, 테스트 collector 등으로 변환한다. 별도 `AgentStreamProjector`나 `AgentStreamEvent`를 core public concept로 두지 않는다.

### `AgentEvent`

`AgentEvent`는 agent-specific event payload다. 별도 `AgentEventRepository`나 `IAgentEventPublisher`를 만들지 않는다. Agent event는 기존 `spakky-event`와 `spakky-outbox`를 사용한다.

`spakky-agent`는 event infrastructure가 아니라 agent event semantics를 정의한다.

## Persistence Contract

Core public persistence port는 다음 세 가지로 제한한다.

- `AgentStateRepository`
- `AgentSignalRepository`
- `AgentEvidenceRepository`

Production in-memory 구현은 제공하지 않는다. Test double/fake는 테스트 코드에만 존재할 수 있다.

### `AgentStateRepository`

`AgentState` 저장, 조회, materialized update를 담당한다.

### `AgentSignalRepository`

`AgentSignal` append/consume을 담당한다. 실행 중 사용자 입력, approval decision, cancel/resume은 durable inbound queue로 취급한다.

### `AgentEvidenceRepository`

`AgentEvidence`, context digest, context manifest, tool/model result evidence를 저장한다. Evidence는 append-only artifact다. Update/delete는 agent-facing interface에 제공하지 않는다.

Redaction/correction은 기존 evidence를 수정하지 않고 새 evidence/event로 append한다.

## Contribution Policy

SQLAlchemy 구현은 `plugins/spakky-sqlalchemy`가 feature contribution으로 제공한다.

```toml
[project.optional-dependencies]
agent = ["spakky-agent>=6.5.0"]

[project.entry-points."spakky.contributions.spakky.agent"]
spakky-sqlalchemy = "spakky.plugins.sqlalchemy.contributions.agent:initialize"
```

Contribution은 다음 구현을 등록한다.

- SQLAlchemy `AgentStateRepository`
- SQLAlchemy `AgentSignalRepository`
- SQLAlchemy `AgentEvidenceRepository`

`spakky-sqlalchemy` base plugin은 `spakky-agent` 설치 여부를 직접 감지하지 않는다. `spakky-agent` feature와 SQLAlchemy provider가 함께 active일 때 contribution loader가 lazy-load한다.

## Model Backplane

LLM 호출은 outbound infrastructure port다. Core interface 이름은 `IAgentModel`이다.

```python
class IAgentModel(Protocol):
    async def complete(self, request: ModelRequest) -> ModelResponse: ...

    def stream(
        self,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]: ...
```

Core는 provider-neutral request/response primitive를 소유한다.

- `ModelRequest`
- `ModelResponse`
- `ModelStreamEvent`
- `ModelMessage`
- `StructuredOutputSpec`
- `ToolCallingSpec`
- `SamplingOptions`
- `StreamingOptions`
- `ModelUsage`

Convenience helper는 가능하지만 adapter conformance는 primitive port 기준으로 검증한다.

### Structured Output And Tool Calling

Structured output과 tool calling은 semantic spec을 분리한다. 둘은 공통 `JsonSchemaConstraint`를 사용한다.

```python
@dataclass(frozen=True)
class JsonSchemaConstraint:
    schema: Mapping[str, object]
    strict: bool = True

@dataclass(frozen=True)
class StructuredOutputSpec:
    constraint: JsonSchemaConstraint
    output_type: type | None

@dataclass(frozen=True)
class ToolCallingSpec:
    tools: Sequence[ModelToolSpec]
    choice: ToolChoice
```

### vLLM Adapter

`plugins/spakky-vllm`은 첫 공식 `IAgentModel` 구현이다.

- vLLM OpenAI-compatible HTTP server에 연결한다.
- 첫 마일스톤은 HTTP API만 지원한다. In-process vLLM Python engine은 포함하지 않는다.
- Streaming은 vLLM/OpenAI-compatible SSE를 소비해 `ModelStreamEvent`로 변환한다.
- TCP/SSE 연결 자체의 IP 변경 내성은 보장하지 않는다.
- Stream disconnect는 표준 interrupted/failure event로 변환하고, action-boundary recovery 정책에 맡긴다.
- Byte-perfect generation resume은 보장하지 않는다.

## Tool Contract

Tool public DX는 decorator 기반이다.

```python
@Pod
class DocsTools:
    @agent_tool(
        permissions=[DocsRead()],
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        evidence=EvidenceCapture.structured(),
    )
    async def search_docs(self, query: str, limit: int = 5) -> SearchDocsResult:
        ...
```

`@agent_tool`은 함수 시그니처를 정본으로 삼는다.

- 입력/출력 타입 hint에서 JSON Schema를 생성한다.
- 내부 synthetic dataclass DTO를 만들지 않는다.
- decoded JSON output을 validation/coercion한 뒤 `inspect.Signature` binding으로 `*args`/`**kwargs` 호출한다.
- schema/binding 불가능하면 registration/startup 단계에서 fail한다.

허용되는 타입은 JSON-compatible 또는 explicit string-compatible이어야 한다.

첫 core 구현은 `@agent_tool` descriptor 생성 시 함수 signature와 resolved type hint만 사용해 `AgentToolSchemaHandle.input_schema` / `output_schema`를 생성한다. 입력은 `self`/`cls`를 제외한 parameter object schema로 표현하며, Python default가 없는 parameter만 required로 표시한다. 지원 타입은 primitive, enum, dataclass, `list[T]`, `tuple[...]`, `Mapping[str, T]`, optional/union, `Annotated[T, ...]`이다. Binding과 DTO wrapping은 이 단계에서 수행하지 않는다.

Opt-out 타입:

- `Any`
- untyped parameter
- untyped return
- untyped `dict`
- non-string mapping key
- positional-only, `*args`, `**kwargs`
- untyped `list`
- raw `object`
- callable/function parameter
- generator/iterator return
- raw file handle, stream, socket
- secret value

Tool metadata는 문자열 tag가 아니라 typed value object/enum으로 표현한다.

- `ToolPermission`
- `ToolEffects`
- `Idempotency`
- `DataAccess`
- `Externality`
- `TimeoutPolicy`
- `ResultBudget`
- `EvidenceCapture`

`ToolRisk`는 core 정본 metadata로 두지 않는다. Risk는 permission/effects/idempotency/data access/externality에서 handler가 계산할 수 있는 derived/display 정보다.

## Evidence Capture

Tool invocation event는 항상 framework event로 남길 수 있어야 한다. Tool result evidence 저장은 `EvidenceCapture`가 제어한다.

- `NONE`
- `REFERENCE_ONLY`
- `SUMMARY`
- `STRUCTURED`
- `RAW`
- `REDACTED`

기본값은 small JSON-compatible output의 `STRUCTURED`다. 크기, 민감도, policy threshold를 넘으면 `REFERENCE_ONLY` 또는 `REDACTED`로 degrade한다. Raw evidence는 opt-in이다.

## Context Pack And Context Rot

LLM context window는 영속 메모리가 아니라 각 model call에 실리는 `ContextPack`이다. `ContextPack`은 append-only event/evidence/state에서 파생되는 transient view다.

Core는 다음 building block을 제공한다.

- `AgentContextHandler`
- `ContextPack`
- `ContextManifest`
- `ContextDigest`
- `ContextHealthSignal`
- `ContextOptimizationAction`

Raw evidence는 압축 결과로 대체하지 않는다. 압축은 `ContextDigest`라는 derived evidence를 append한다.

Context manifest는 기본 감사 단위다. 전체 prompt snapshot 저장은 debug/audit profile의 선택 기능이다.

Context rot은 prompt injection detector가 아니다. 다음 현상을 다루는 context quality/budget 문제다.

- budget pressure
- stale plan residue
- duplicate evidence
- buried critical evidence
- low-signal tool output
- conflicting facts
- unbounded subtask trace
- instruction drift

Core는 signal vocabulary와 handler hook을 제공한다. 모든 판단 구현을 core가 소유하지 않는다. 단, token budget pressure 같은 보편적 신호는 기본 building block으로 제공할 수 있다.

## Streaming And Interactivity

Token delta는 model adapter에서 `ModelStreamEvent`로 들어오고, agent business logic은 이를 `AgentYield`로 caller에게 흘릴 수 있다.

```text
vLLM SSE stream
  -> IAgentModel.stream(...)
  -> @Agent.execute() yield
  -> inbound adapter
  -> client
```

`@Agent.execute()`의 async generator가 client streaming의 primary source다. Core는 별도 stream projector service를 제공하지 않는다.

실행 중 사용자 입력은 `AgentSignal`로 append된다. Scheduler 또는 application orchestration은 safe boundary에서 signal을 소비한다. Cancel/approval 같은 control signal은 가능한 즉시 반영한다.

## HITL And Cancellation

Approval은 tool에만 묶지 않고 모든 `AgentAction`에 적용할 수 있어야 한다.

- model call
- tool invocation
- delegation
- final publication
- external side effect
- context redaction/compaction
- cancellation/resume

`ApprovalDecision`은 다음을 지원한다.

- `APPROVE`
- `REJECT`
- `MODIFY`
- `DEFER`
- `CANCEL`

Approval required는 `INTERRUPTED(reason=APPROVAL_REQUIRED)`로 표현한다.

Cancel은 control signal로 append된다. 취소가 시작되면 `CANCELLING`이 되고, model/tool/subagent에는 cancellation token을 전달한다. 정리 성공 시 `CANCELLED`, cleanup 실패 시 `FAILED(reason=CANCELLATION_CLEANUP_FAILED)`가 된다.

## Delegation

Subagent delegation은 core building block으로 제공한다. First-class target은 다른 `@Agent` component다. 외부 delegate(MCP/A2A/remote agent)는 adapter가 normalize한다.

Core는 다음을 제공한다.

- `IAgentDelegate`
- `DelegationPacket`
- `DelegationResult`
- `DelegationBudget`
- parent/child linkage metadata

Parent context full fork는 기본이 아니다. `AgentContextHandler` 또는 delegation handler가 child용 context projection을 만든다. 기본은 minimal task packet이다.

`DelegationPacket`은 다음을 포함한다.

- parent state id
- delegation id
- goal
- constraints
- selected evidence refs
- allowed capabilities
- expected output schema
- budget/deadline
- return policy

Child result는 summary/evidence/ref 중심으로 부모에게 반환한다. Raw child trace를 부모 context에 무조건 주입하지 않는다.

## Recovery And Idempotency

마일스톤은 durable action-boundary resume을 완성해야 한다.

- `ACTIVE`/`INTERRUPTED` state는 restart 후 resume 가능해야 한다.
- Terminal state는 resume 불가다.
- 완료 기록이 있는 action은 재실행하지 않는다.
- idempotent incomplete action은 retry/resume 가능하다.
- non-idempotent incomplete action은 `INTERRUPTED(reason=RECOVERY_REQUIRES_HITL)`로 전환한다.
- in-flight stream의 byte-perfect resume은 보장하지 않는다.

Action idempotency는 표준 metadata로 표현한다.

- `IDEMPOTENT`
- `NON_IDEMPOTENT`
- `CONDITIONALLY_IDEMPOTENT`
- `UNKNOWN`

`UNKNOWN` 또는 unsafe incomplete action은 recovery 시 HITL을 요구한다.

## Sensitive Data And Safety

Secret은 LLM-facing context, schema, evidence payload에 텍스트로 들어갈 수 없다. Secret은 redact 대상이 아니라 non-contextual capability로 다룬다.

Core는 다음 building block을 제공한다.

- `CredentialRef`
- `SecretRef`
- `SecretField`
- `SensitiveField`
- `DataSensitivity`
- `PII`
- `MaskingPolicy`
- `RedactionPolicy`
- `ContextExposurePolicy`
- `EvidenceExposurePolicy`

민감도 metadata는 `typing.Annotated`를 사용한다.

```python
@dataclass(frozen=True)
class CustomerProfile:
    name: Annotated[str, SensitiveField(PII.NAME)]
    email: Annotated[str, SensitiveField(PII.EMAIL)]
    account_id: str
```

Annotated metadata는 내부 descriptor에 항상 보존한다. JSON Schema extension은 policy가 허용할 때만 LLM-facing schema에 포함한다.

민감정보 보호는 LLM에게 "출력하지 말라"고 프롬프트로 권유하는 방식에 의존하지 않는다. Schema extraction, context assembly, evidence capture, model input/output boundary에서 deterministic guard를 제공해야 한다.

Streaming output guard는 profile-driven이다.

- `LOW_LATENCY`
- `BALANCED`
- `STRICT`
- `NO_STREAM_UNTIL_FINAL_GUARDED`

기본값은 `BALANCED`다. Final aggregate guard는 항상 실행한다. Pattern/heuristic PII detector는 extension 영역이고, core는 detector를 내장하지 않는다.

## Handler Surface

Core는 과도한 policy object 대신 명확한 handler 개입 지점을 제공한다.

- `AgentApprovalHandler`
- `AgentContextHandler`
- `AgentOutputGuard`
- `AgentRecoveryHandler`
- `AgentToolHandler`

`Handler`는 판단/개입 지점이고, `Callback`은 단순 알림/side effect hook에만 사용한다.

## Required Use Cases

마일스톤은 다음 유즈케이스를 모두 실제 실행 가능하게 만든다.

1. `@Agent` class를 DI container에 등록한다.
2. `@Agent.execute()`가 `Generator[AgentYield[OutputT], None, None]` 또는 `AsyncGenerator[AgentYield[OutputT], None]`로 streaming result를 반환한다.
3. Simple output return을 `Final(output)` convenience로 처리한다.
4. `@Agent` metadata, `execute()` signature, DI graph, contribution registry가 함께 검증된다.
5. `IAgentModel`을 통해 vLLM OpenAI-compatible server를 호출한다.
6. vLLM streaming token을 `AgentYield`로 client에 전달한다.
7. `@agent_tool` decorated method의 signature에서 JSON Schema를 생성한다.
8. vLLM structured output/constrained decoding으로 tool arguments를 생성하고 `*args`/`**kwargs`로 호출한다.
9. Schema-incompatible tool signature는 startup early fail한다.
10. Tool result evidence capture policy가 동작한다.
11. `AgentStateRepository`, `AgentSignalRepository`, `AgentEvidenceRepository`가 SQLAlchemy contribution으로 제공된다.
12. Production in-memory persistence 없이 local app이 SQLAlchemy contribution으로 실행된다.
13. Approval required action에서 state가 `INTERRUPTED`로 전환되고 signal로 승인/거절/수정 후 이어간다.
14. Cancel signal이 `CANCELLING`/`CANCELLED`로 전환된다.
15. Process restart 후 active/interrupted state를 action boundary에서 resume한다.
16. Non-idempotent incomplete action은 recovery HITL로 전환된다.
17. Delegation packet으로 다른 `@Agent`에 bounded task를 위임한다.
18. Context manifest/digest가 evidence로 append된다.
19. Annotated sensitive metadata가 schema/context/evidence/output guard에 전달된다.
20. Secret type은 LLM-facing schema/context/evidence로 노출되지 않는다.
21. Existing `spakky-event`/`spakky-outbox`로 `AgentEvent`를 발행/저장할 수 있다.
22. FastAPI 같은 inbound adapter가 `AgentYield` generator를 SSE/WebSocket으로 직접 서빙할 수 있다.
23. Claude Code-like `CodeAssistant` 예제가 workspace read/write, shell, git tool, vLLM streaming, approval, signal, evidence, restart/resume을 통합해 동작한다.

## 고려한 대안

### 대안 A: 단일 LLM SDK wrapper

`run(prompt) -> response` 형태의 단순 실행 API를 제공한다.

기각 이유:

- `@UseCase`와 동격인 business workflow component가 되지 못한다.
- streaming, signal, recovery, evidence, HITL을 담기 어렵다.
- Spakky의 DDD/hexagonal model과 결합력이 약하다.

### 대안 B: 기존 agent framework adapter

Pydantic AI 또는 LangGraph를 reference runtime으로 선택하고 Spakky wrapper를 제공한다.

기각 이유:

- `spakky-agent`가 기존 framework 하위 adapter처럼 보인다.
- `@Agent` stereotype, state/signal/evidence, contribution persistence 같은 Spakky-native contract가 흐려진다.
- 기술 선택보다 application architecture contract가 더 중요하다.

### 대안 C: Agent-specific adapter package matrix

`spakky-agent-fastapi`, `spakky-agent-typer`, `spakky-agent-mcp`, `spakky-agent-a2a`, `spakky-agent-sqlalchemy`를 만든다.

기각 이유:

- Plugin 수가 폭증한다.
- Inbound adapter는 application 개발자가 기존 Spakky building block으로 만들 수 있는 영역이다.
- SQLAlchemy 구현은 ADR-0010 contribution policy로 해결해야 한다.

### 대안 D: Spakky-native `@Agent` + vLLM-first model adapter + contribution persistence

채택한다.

장점:

- `@Agent`를 `@UseCase`와 동격으로 모델링한다.
- Core가 정말 필요한 building block만 제공한다.
- 오픈소스/무료/로컬 실행 가능한 vLLM-first 경로를 제공한다.
- ADR-0010 contribution policy와 일관된다.
- Adapter/package 폭증을 피한다.

단점:

- 단일 마일스톤 범위가 크다.
- Core contract 설계 실수가 이후 extension 전체에 영향을 준다.
- vLLM local execution 환경 검증이 필요하다.

## 결과 (Consequences)

### 긍정적

- Agent를 LLM wrapper가 아닌 application workflow component로 모델링한다.
- 기존 Spakky DI, Pod, event, outbox, contribution 정책과 정렬된다.
- Framework 사용자는 `@Agent`, `@agent_tool`, `IAgentModel`만으로 agentic use case를 작성할 수 있다.
- vLLM-first로 무료 로컬 실행 경로가 생긴다.
- FastAPI/Typer/gRPC 같은 inbound adapter는 기존 plugin building block을 재사용한다.

### 부정적

- 마일스톤이 매우 크고 ambitious하다.
- `@Agent`의 UseCase 치환성을 유지하면서 long-running recovery까지 구현해야 한다.
- Streaming safety와 민감정보 guard는 완전한 PII 탐지 보장을 제공하지 않으므로 profile/handler 문서화가 중요하다.

### 중립적

- Pydantic AI/LangGraph/LiteLLM은 배제하지 않는다. 첫 마일스톤의 정본이 아닐 뿐이다.
- vLLM in-process engine은 첫 마일스톤에 포함하지 않는다.
- SaaS 제품 구현은 Framework 범위 밖이다.

## 검증 기준

- `core/spakky-agent`는 외부 LLM SDK, DB, protocol server에 직접 의존하지 않는다.
- `@Agent`는 `@UseCase`와 같은 Pod stereotype으로 DI 등록된다.
- `@Agent.execute()` direct invocation이 business logic invocation으로 가능하다.
- Bootstrap validation이 `@Agent` metadata, `execute()` signature, DI graph, contribution registry를 함께 검사하고 missing contribution을 startup fail로 만든다.
- Core에는 production in-memory repository 구현이 없다.
- `plugins/spakky-vllm`이 local vLLM OpenAI-compatible server에 대해 complete/stream을 검증한다.
- `@agent_tool` signature schema extraction과 early fail이 테스트된다.
- `AgentStateRepository`, `AgentSignalRepository`, `AgentEvidenceRepository` SQLAlchemy contribution이 로드된다.
- Approval, cancel, restart/resume, non-idempotent recovery HITL이 통과한다.
- Annotated sensitive metadata와 secret exclusion guard가 테스트된다.
- `AgentYield` async generator를 inbound adapter가 streaming response로 서빙하는 예제가 동작한다.
- `uv run mkdocs build --strict`가 통과한다.

## 티켓화 기준

이 ADR 직후 생성되는 GitHub Issues는 조사 티켓이 아니라 구현 티켓이어야 한다. 기술 선택은 본 ADR에서 완료되었다.

티켓은 다음 축을 모두 포함해야 한다.

- `core/spakky-agent` package skeleton과 `@Agent` stereotype
- `AgentExecutionSpec`, `AgentState`, `AgentSignal`, `AgentYield`, `AgentEvidence`
- `IAgentModel`, `ModelRequest`, `ModelResponse`, `ModelStreamEvent`
- `plugins/spakky-vllm`
- `@agent_tool` schema extraction/binding/metadata
- sensitive metadata/secret exclusion/output guard
- context pack/manifest/digest/context handler
- approval/cancel/signal handling
- recovery/idempotency/action-boundary resume
- delegation between `@Agent` components
- SQLAlchemy contribution for state/signal/evidence repositories
- integration examples using existing inbound adapter building blocks
- Claude Code-like coding assistant integration example
- conformance tests
- README, guide, API docs, ARCHITECTURE sync

## 참고 자료

- [ADR-0010: Feature Contribution Policy](0010-feature-contribution-policy.md)
- [vLLM OpenAI-Compatible Server](https://docs.vllm.ai/en/stable/getting_started/quickstart/#openai-compatible-server)
- [vLLM Structured Outputs](https://docs.vllm.ai/en/stable/features/structured_outputs.html)
- [Model Context Protocol Tools Specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- [AG-UI Overview](https://docs.ag-ui.com/introduction)
- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)
