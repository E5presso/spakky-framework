# spakky-agent

> `spakky-agent`는 ADR-0009 Agentic Hexagonal Architecture의 core contract 패키지입니다.
> Agent를 LLM SDK wrapper가 아니라 `@UseCase`와 같은 application workflow component로 다루기 위한 public 타입 표면을 제공합니다.

## 언제 필요한가

- agentic workflow를 Spakky DI/hexagonal architecture 안에서 표현하려는 경우
- spec과 `@agent_tool` 메서드만 선언하고 프레임워크가 표준 실행 루프(`execute()`)를 자동 제공하게 하려는 경우
- `AgentYield` stream을 FastAPI, WebSocket, CLI 같은 inbound adapter가 직접 소비하게 하려는 경우
- model adapter를 `IAgentModel` outbound port로 구현하려는 경우
- long-running execution의 state, signal, evidence 계약을 plugin contribution으로 구현하려는 경우

## 설치

Core contract만 사용할 때는 `spakky-agent`를 설치합니다.

```bash
pip install spakky-agent
```

로컬 vLLM model adapter와 SQLAlchemy durable repository를 함께 쓰는 일반적인 ADR-0009 조합은 다음처럼 설치합니다.

```bash
pip install spakky-agent spakky-vllm "spakky-sqlalchemy[agent]"
```

`spakky-agent`는 public API와 bootstrap validation만 제공합니다. Production state/signal/evidence repository는 `spakky.contributions.spakky.agent` provider contribution으로 들어와야 하며, 운영용 in-memory persistence fallback은 없습니다.

## 제공하는 public surface

- `Agent`, `AgentExecutionSpec`, `AgentExecutionLimits`: `@UseCase`와 동격인 Pod stereotype과 보조 실행 의미. `AgentExecutionSpec`은 실행 이름/목표(`name`, `objective`), system-level 지시문(`instructions`), 구조화 출력 타입(`output_type`), 수신 signal/recovery/streaming/timeout 선언(`accepted_signals`, `recovery`, `streaming_exposure_mode`, `timeout_seconds`, `limits`), 협력 agent(`teammates`), 컨텍스트 압축 정책(`compaction`), 위임 허용 marker(`delegation_allowed`), 문자열 metadata(`metadata`)를 보존한다. 공백 name/objective/instructions, non-class `output_type`, 중복 teammate 이름, 모순되는 timeout 선언은 `AgentDefinitionError`로 거부된다. `execute()` 없이 spec + `@agent_tool` 메서드만 선언하면 프레임워크가 `AgentRunner` 기반 표준 루프를 `execute()`로 자동 바인딩한다(ADR-0013 §1). 개발자가 직접 `execute()`를 작성한 경우에는 건드리지 않는다.
- `AgentRunner`, `AgentRunResult`: 프레임워크가 소유하는 표준 실행 루프. `AgentRunner.for_agent_instance(instance)`는 인스턴스에 주입된 속성을 타입 기반으로 탐색해 `IAgentModel`·`IAgentStateRepository`·`IAgentSignalRepository`·`IAgentEvidenceRepository`를 resolve한다. 같은 orchestration 위에 두 stream을 노출한다 — `run(run_input)`은 inbound adapter가 직접 소비하는 public `AsyncGenerator[AgentYield[object], None]`을, `run_events(run_input)`은 AG-UI·A2A 어댑터가 무손실로 투영하는 프로토콜 중립 `AsyncGenerator[AgentEvent, None]`을 yield한다. `run_events()`는 모델 스트림의 message/reasoning delta와 tool call `start`·`args-delta`·`end`·`result` lifecycle을 구분된 `AgentEvent`로 방출하고, 루프 경계를 `RunStartedEvent`/`StepStartedEvent`/`StepFinishedEvent`/`RunPausedEvent`/`RunFinishedEvent`로 감싼다(ADR-0013 §3). 승인·auth 인터럽트는 성공 종료가 아니라 `RunPausedEvent`로 방출된다. `accepted_signals`/`RecoveryStrategy.ACTION_BOUNDARY` 선언이 없는 stateless agent는 model → tool → final의 단순 경로를 실행하고, durable agent는 state 전이·signal 소비·HITL pause→approval→resume 흐름·action boundary checkpoint까지 모두 처리한다. 두 stream 모두 durable approval gating과 evidence persistence를 공유한다. `AgentRunResult`는 spec이 `output_type`을 선언하지 않을 때 기본으로 반환되는 중립 종료 요약 dataclass(`state_id`, `status`, `tool_calls`, `evidence_count`)다.
- `RunAgentInput`: inbound run 계약. `state_id`(실행 상관 ID), `instruction`(모델 요청의 사용자 프롬프트), `conversation_id`(멀티턴 스레드 ID, 생략 시 `state_id`로 대체), `parent_run_id`(위임 child run이 parent run과 연결되는 중립 링크), `resume`(일시 중단된 실행 재개 여부), `message_history`(클라이언트가 주입한 이전 대화 이력 `tuple[ModelMessage, ...]`, ADR-0013 §6 client-injected history), `metadata`(model request metadata에 병합되는 runner 레벨 부가 정보)를 담는다. `effective_conversation_id` property는 `conversation_id or state_id`를 반환한다. approval decision은 이 계약이 아닌 signal repository를 통해 전달된다.
- `AgentTeammate`: 이름과 로컬 Pod 타입(`pod`) 또는 원격 AgentCard http(s) URL(`card_url`) 중 정확히 하나를 선언하는 협력 agent 기술자. 둘 다 지정하거나 둘 다 생략하면 `AgentDefinitionError`. `@Agent`는 teammate마다 `teammate.<schema_token(name)>.delegate` synthetic tool descriptor를 생성하며, schema token은 소문자화 후 non-alphanumeric 문자를 `_`로 치환한 값이다. 로컬 teammate는 parent에 주입된 child Pod를 찾아 `AgentRunner.run_events()`로 in-process 실행하고, 원격 teammate는 parent에 주입된 `IAgentDelegate` port로 위임한다.
- `ICompactionStrategy`: 교체 가능한 컨텍스트 압축 포트(`ABC`). `async compact(history: tuple[ModelMessage, ...], usage: ModelUsage, capability: ModelCapability) -> tuple[ModelMessage, ...]`를 구현하며, 이력을 더 짧은 이력으로 변환하는 순수 transform이다. pydantic-ai의 message history processor / `ProcessHistory` capability를 참조하되 usage·capability를 명시 파라미터로 받아 압축 강도를 조절한다(ADR-0013 §7).
- 내장 전략 4종:
    - `KeepRecentMessagesCompactionStrategy(max_messages)`: 슬라이딩 윈도우 — 가장 최근 `max_messages`개만 남긴다.
    - `TrimToolResultsCompactionStrategy(max_characters)`: `TOOL` role 메시지 내용만 `max_characters`까지 잘라 user/assistant 대화는 보존한다.
    - `SummarizeOldTurnsCompactionStrategy(model, keep_recent, summary_instruction)`: 보조 모델(`IAgentModel.complete`)로 `keep_recent` 이전 턴을 단일 `EVIDENCE` 요약 메시지로 대체한다.
    - `ProviderManagedCompactionStrategy()`: 프로바이더가 자체 압축을 소유하는 backend용 passthrough(이력 무변경).
- `AgentCompactionPolicy`: 압축 전략 체인(`strategies: tuple[ICompactionStrategy, ...]`, 비어 있으면 거부)과 트리거 토큰 임계값(`trigger_token_threshold: int`, 양수 필수)을 선언하는 값 타입. `AgentRunner`는 `_resolve_history`가 만든 이력의 추정 토큰이 임계값을 넘으면 선언 순서대로 전략 체인을 자동 적용한 뒤 모델 요청에 싣는다(매 턴, `ModelCapability.context_window_tokens` + 현재 usage 기준). 토큰 추정은 코어가 프로토콜 중립을 유지하므로 transcript 길이의 ~4자/토큰 근사를 쓴다.
- `AgentYield`: `execute()`가 caller에게 흘려보내는 typed stream item
- `AgentEvent`, `AgentEventKind`, `AgentEventAttribution`: AG-UI·A2A 같은 stream protocol adapter가 무손실로 변환하는 프로토콜 중립 이벤트 taxonomy. message/reasoning delta, tool call(start·args delta·end·result), run/step 수명주기, state(snapshot·delta), artifact를 구분하며, 모든 이벤트가 `agent_id`(attribution) + `parent_run_id`(위임 parent link, 루트는 `None`) + `conversation_id`(thread/context)를 운반합니다. AG-UI `runId`/`parentRunId`/`threadId`와 A2A `taskId`/parent task/`contextId`로 1:1 매핑됩니다. MCP는 이 이벤트 stream을 소비하지 않고 agent tool catalog를 외부 MCP server와 병합하거나 MCP server로 노출합니다. 도구 호출 이벤트는 메시지 연결을 추가로 보존합니다 — `ToolCallResultEvent.message_id`(도구 결과가 귀속되는 대화 메시지, AG-UI `messageId` 필수 필드)와 `ToolCallStartEvent.parent_message_id`(도구 호출을 요청한 상위 메시지, AG-UI `parentMessageId`, 없으면 `None`)
- `AgentState`: long-running agent execution의 materialized lifecycle state
- `AgentSignal`: 실행 중 들어오는 user message, approval, cancel 같은 inbound stimulus
- `AgentSignalPollPoint`, `consume_pending_agent_signals`: safe boundary나 configured poll point에서 durable signal queue를 대기 없이 소비하는 helper
- `on_signal`, `discover_agent_signal_hooks`, `AgentSignalHookCatalog`: 선언형 시그널 훅(ADR-0013 §1). `@on_signal(kind)`는 `@agent_tool`과 같은 선언형 seam으로, `async def m(self, signal: AgentSignal) -> AsyncGenerator[AgentYield[object], None]` 메서드를 표시한다. `Agent` discovery가 `@agent_tool`과 동일한 MRO 워크로 훅을 수집해 `signal_hook_catalog`에 담고, runner가 해당 종류 시그널을 소비하는 poll 지점에서 자동 호출하여 yield된 item을 public stream으로 흘려보낸다. `CANCEL`·`APPROVAL_DECISION`은 runner 전용 단계가 처리하므로 훅 대상에서 제외되고, 훅이 없는 `USER_MESSAGE`는 기본 progress로 폴백한다. 계약 위반(비 async generator, `signal: AgentSignal` 외 인자, `AgentYield` 외 yield 타입)은 정의 시점에 `AgentDefinitionError`로 거부된다.
- `AgentApprovalRequest`, `plan_agent_tool_approval`, `parse_agent_approval_decision_signal`: 위험 boundary에서만 HITL approval을 요구하고 decision signal을 typed state target으로 해석하는 helper
- `begin_agent_cancellation`, `run_agent_cancellation_cleanup`, `complete_agent_cancellation`: cancel signal을 `CANCELLING`으로 materialize하고 model stream/tool/delegate cleanup hook 결과를 evidence와 terminal state에 반영하는 helper
- `AgentEvidence`: tool/model/context 판단 근거를 위한 append-only artifact
- `AgentEvidenceCandidate`: tool result와 model/tool decision을 append-only evidence 후보로 변환하는 contract
- `AgentActionBoundaryCheckpoint`, `plan_agent_resume`: model call, tool call, approval wait 전후 checkpoint evidence와 restart/resume 결정 helper
- `DelegationPacket`, `DelegationResult`, `IAgentDelegate`: 다른 `@Agent` component로 작업을 위임하고 parent evidence/stream에 결과를 연결하는 계약
- `ContextPack`, `ContextManifest`, `ContextDigest`: model input context와 audit/digest evidence를 위한 typed contract
- `ContextHealthSignal`, `ContextRotSymptom`, `ContextOptimizationAction`: context rot 관찰 결과와 압축/refresh/delegation/slice drop action metadata
- `SensitiveField`, `SecretField`, `CredentialRef`, `SecretRef`, `ContextExposurePolicy`, `EvidenceExposurePolicy`: `typing.Annotated` 민감 metadata와 deterministic guard 정책
- `StreamingSensitivePattern`, `StreamingRedactionPolicy`, `StreamingRedactionSession`: chunk boundary를 가로지르는 sensitive output pattern을 bounded buffer로 redaction하고 final audit evidence/error를 생성하는 streaming guard 계약
- `IAgentStateRepository`, `IAgentSignalRepository`, `IAgentEvidenceRepository`: persistence provider가 구현하는 core port
- `ITaskStore`, `ConversationTurn`: 멀티턴 대화 이력을 `conversation_id`로 영속하는 server-side session 계약(ADR-0013 §6). `load_history(conversation_id)`로 이전 transcript를 조회하고 `append_turns(conversation_id, turns)`로 user/assistant turn을 누적한다. `conversation_id`는 AG-UI `threadId`와 A2A `contextId`로 투영될 수 있는 프로토콜 중립 키입니다. 단, A2A protocol `Task` snapshot 영속은 `spakky-a2a`의 `IA2ATaskRepository`/`SpakkyA2ATaskStore` 책임이고 core `ITaskStore`와 분리됩니다. `ConversationTurn`은 transcript 단위(user/assistant role + content)이며 history 재생 시 `as_model_message()`로 model 요청 메시지로 투영된다. `AgentRunner`는 `message_history`가 주입되면 그 이력을 우선해 시드하고(stateless, store 미기록), 아니면 store의 영속 이력을 시드한 뒤 완료 시 turn을 기록한다 — 두 경로는 run마다 상호 배타적이다.
- `IAgentModel`: vLLM 등 model backend가 구현하는 outbound port. `capability` property로 backend 능력을 런타임 전에 노출
- `ModelCapability`: reasoning 지원 여부, `context_window_tokens` 한도, token counting 지원 여부를 run 이전에 조회할 수 있는 descriptor
- `ModelRequest`, `ModelResponse`, `ModelStreamEvent`: provider-neutral model 호출/응답/stream 계약
- `ToolCallingSpec`, `ModelToolSpec`, `ModelToolCall`: model-facing tool call 요청과 후보 결과
- `agent_tool`, `AgentToolBoundInvocation`, `AgentToolBindingError`, `ToolEffects`, `ToolRisk`, `ToolApprovalRequirement`, `ToolResumeMetadata`, `EvidenceCapture`: tool binding, risk, approval, idempotency, evidence capture metadata
- `AgentToolDispatcher`, `AgentToolDispatchError`: model tool-call을 카탈로그 descriptor로 조회·자동 바인딩·실행하는 디스패치 building block과 미등록 도구 에러

## 의존성 경계

Core package는 `spakky` core에만 의존합니다. vLLM, SQLAlchemy, FastAPI, Typer 같은 infrastructure dependency를 직접 import하지 않습니다.

운영용 persistence fallback도 제공하지 않습니다. State, signal, evidence repository 구현은 SQLAlchemy 등 provider plugin의 feature contribution으로 등록되어야 하며, 누락 시 bootstrap 단계에서 custom error로 실패해야 합니다.

Durable 실행 경로는 `AgentExecutionSpec.recovery == RecoveryStrategy.ACTION_BOUNDARY` 또는 `accepted_signals` 선언에서 파생됩니다. 이 경우 bootstrap은 `IAgentStateRepository`, `IAgentSignalRepository`, `IAgentEvidenceRepository`가 모두 등록되어 있는지 검증하고, 누락 시 필요한 repository type과 설치해야 할 `spakky-sqlalchemy[agent]` / `spakky.contributions.spakky.agent` provider contribution을 error message에 포함합니다. 운영용 in-memory repository fallback은 없습니다.

`AgentEvidenceRepository`의 agent-facing interface는 append/read 계열만 노출합니다. Redaction, correction, context digest 갱신은 기존 evidence를 수정하지 않고 새 evidence를 append하는 방식으로 표현합니다.

## 사용 예시

### 선언형 — 프레임워크 제공 루프 (권장)

spec과 `@agent_tool` 메서드만 작성하면 `@Agent`가 `AgentRunner` 기반 표준 루프를 `execute()`로 자동 바인딩합니다. `RunAgentInput`을 인자로 받아 `AgentYield` 스트림을 내보내는 표준 루프가 model → tool dispatch → HITL pause/resume → state 전이 → final 까지 처리합니다.

```python
from spakky.agent import (
    Agent,
    AgentExecutionSpec,
    IAgentModel,
    agent_tool,
)


@Agent(
    spec=AgentExecutionSpec(
        name="file_agent",
        instructions="Use the declared tools to read and summarize files.",
    )
)
class FileAgent:
    def __init__(self, model: IAgentModel) -> None:
        self.model = model

    @agent_tool(schema_name="file.read")
    async def read_file(self, path: str) -> str:
        with open(path) as f:
            return f.read()
    # execute()를 작성하지 않으면 AgentRunner 기반 표준 루프가 자동으로 제공된다.
```

호출 측은 `RunAgentInput`을 구성해 `execute()`를 호출합니다.

```python
from spakky.agent import RunAgentInput

run_input = RunAgentInput(state_id="run-001", instruction="Read README.md and summarize.")
async for item in agent_instance.execute(run_input):
    print(item)
```

실행 중 들어오는 시그널에 커스텀 반응이 필요하면 `@on_signal`을 선언합니다 — 루프 본문을 작성하지 않고 시그널 종류별 핸들러만 선언하면 runner가 자동 호출합니다.

```python
from collections.abc import AsyncGenerator

from spakky.agent import (
    AgentSignal,
    AgentSignalKind,
    AgentYield,
    AgentYieldKind,
    Progress,
    on_signal,
)


class FileAgent:
    @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
    async def on_steering(
        self,
        signal: AgentSignal,
    ) -> AsyncGenerator[AgentYield[object], None]:
        yield AgentYield(
            kind=AgentYieldKind.PROGRESS,
            payload=Progress(
                f"steering: {signal.payload.get('instruction')}",
                current_step="steering",
            ),
        )
```

### 커스텀 execute() 탈출 경로

자동 제공 루프로 표현할 수 없는 커스텀 제어가 필요한 경우에만 `execute()`를 직접 작성합니다. 이 경우 자동 바인딩은 적용되지 않으며, `execute()` 본문이 전체 실행을 책임집니다.

```python
from collections.abc import AsyncGenerator

from spakky.agent import (
    Agent,
    AgentExecutionLimits,
    AgentExecutionSpec,
    AgentSignalKind,
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


@Agent(
    spec=AgentExecutionSpec(
        name="code_assistant",
        objective="inspect and edit a workspace",
        accepted_signals=(
            AgentSignalKind.USER_MESSAGE,
            AgentSignalKind.APPROVAL_DECISION,
            AgentSignalKind.CANCEL,
        ),
        limits=AgentExecutionLimits(timeout_seconds=300),
    )
)
class CodeAssistant:
    def __init__(self, model: IAgentModel) -> None:
        self.model = model

    async def execute(
        self,
        command: str,
    ) -> AsyncGenerator[AgentYield[Final[str]], None]:
        request = ModelRequest(
            messages=(ModelMessage(ModelMessageRole.USER, command),),
        )
        async for event in self.model.stream(request):
            if event.kind == ModelStreamEventKind.TOKEN_DELTA:
                yield AgentYield(
                    kind=AgentYieldKind.TOKEN,
                    payload=Token(event.token_delta or ""),
                )

        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(output=command, metadata={}),
        )
```

`@Agent`는 `@Pod` 계열 stereotype이므로 application scan과 constructor DI에 참여합니다. spec과 `@agent_tool` 메서드만 선언하고 `execute()`를 작성하지 않으면 프레임워크가 `AgentRunner` 기반 표준 루프를 `execute()`로 자동 바인딩합니다(ADR-0013 §1). 커스텀 제어가 필요한 경우에만 `execute()`를 직접 작성하며, 이 경우 자동 바인딩은 적용되지 않습니다. `execute()`는 `Generator[AgentYield[T], None, None]` 또는 `AsyncGenerator[AgentYield[T], None]`로 typed stream item을 yield할 수 있고, non-generator 반환형은 streaming 없는 직접 결과 계약으로 취급됩니다. Inbound adapter가 SSE/WebSocket/CLI처럼 진행 상태를 즉시 내보내야 한다면 `AgentYield` generator 계약을 사용해야 합니다.

`AgentYieldKind`의 public status vocabulary는 `token`, `progress`, `tool`, `evidence`, `approval`, `final`, `error`, `cancel`입니다. 각 item의 payload는 `Token`, `Progress`, `Tool`, `Evidence`, `Approval`, `Final[T]`, `Error`, `Cancel` value object로 구분되므로 inbound adapter는 별도 stream projector 없이 generator를 직접 순회해 transport별 이벤트로 바꿀 수 있습니다.

HITL approval은 모든 action 앞에 자동 삽입되는 step이 아니라 risk boundary에서만 materialize됩니다. `plan_agent_tool_approval()`은 `@agent_tool` descriptor의 `ToolRisk`와 `ToolApprovalRequirement`를 읽어 low-risk 또는 `NOT_REQUIRED` tool은 `PROCEED`로 돌려보내고, side-effect/write/network/destructive 후보만 `AgentState(status=INTERRUPTED, transition=WAITING_APPROVAL, reason=APPROVAL_REQUIRED)`와 `AgentYieldKind.APPROVAL` item으로 바꿉니다. `run_events()`는 이 상태를 성공 `RunFinishedEvent`로 덮지 않고, prompt·approval id·tool call id·allowed decisions를 담은 `RunPausedEvent`로 방출합니다. Auth 인터럽트는 `AgentStateReason.AUTH_REQUIRED`로 구분되어 A2A 같은 어댑터가 `auth-required`를 직접 투영할 수 있습니다. Inbound adapter가 approval decision signal을 append하면 `parse_agent_approval_decision_signal()`이 `approve`, `reject`, `modify`, `defer`, `cancel`을 typed outcome으로 해석합니다. `approve`/`modify`는 `ACTIVE/RUNNING`, `defer`는 계속 `INTERRUPTED/WAITING_APPROVAL`, `reject`는 `FAILED`, `cancel`은 `CANCELLING`으로 분리되므로 approval wait와 cancellation/failure lifecycle이 섞이지 않습니다.

실행 중 inbound adapter가 user message, approval decision, cancel, resume signal을 append하면 orchestration은 safe boundary, action boundary, model stream tick 같은 poll point에서 `consume_pending_agent_signals()`를 호출합니다. 이 helper는 sleep/poll loop 없이 현재 pending queue만 읽고 append order의 eligible prefix를 consumed 처리하므로 token streaming을 불필요하게 block하지 않습니다. Repository 구현은 `list_pending()` 결과를 append/queue order로 반환해야 하며, helper는 earlier unaccepted signal을 건너뛰어 later signal을 먼저 소비하지 않습니다.

Cancel은 즉시 terminal state로 뭉개지지 않습니다. Orchestration은 `begin_agent_cancellation()`으로 durable state를 `CANCELLING(reason=CANCELLATION_REQUESTED)`으로 먼저 저장하고, 실행 중인 model stream, tool execution, delegate execution을 `AgentCancellationCleanupTask` hook으로 정리합니다. `run_agent_cancellation_cleanup()`은 각 hook outcome을 `AgentCancellationCleanupReport`로 모으고, `report.to_evidence_candidate()`는 append-only `AgentEvidenceKind.CANCELLATION` evidence를 남깁니다. 모든 cleanup이 성공하거나 skipped이면 `complete_agent_cancellation()`은 `CANCELLED`로 끝내고, 하나라도 실패하면 `FAILED(reason=CANCELLATION_CLEANUP_FAILED)`로 끝냅니다. 일반 실패(`FAILED(reason=EXECUTION_FAILED)`), timeout(`FAILED(reason=TIMEOUT)`), user interruption(`INTERRUPTED(...)`), cancellation(`CANCELLED(reason=CANCELLATION_REQUESTED)`)은 state reason과 recovery 의미가 분리됩니다.

Action-boundary recovery는 model call, tool call, approval wait 전후에 `AgentActionBoundaryCheckpoint`를 append-only `AgentEvidenceKind.ACTION_BOUNDARY` evidence로 저장하는 방식으로 표현합니다. Restart 후 scheduler나 application orchestration은 `IAgentStateRepository`가 반환한 state, `IAgentSignalRepository`의 pending signal, `IAgentEvidenceRepository`의 state evidence만으로 `plan_agent_resume()`을 호출해 다음 동작을 복원합니다. 마지막 boundary가 completed이면 `SKIP_COMPLETED`로 중복 실행을 피하고, incomplete idempotent action이면 `RETRY`를 반환합니다. Incomplete non-idempotent/unknown action 또는 unresolved approval wait는 state를 `INTERRUPTED` / `RECOVERY_REQUIRES_HITL`로 materialize해 자동 재실행하지 않습니다.

`@agent_tool` descriptor는 Python 함수 signature와 type hint를 정본으로 삼아 `AgentToolSchemaHandle.input_schema` / `output_schema`에 model-facing JSON schema를 보존합니다. 입력 schema는 `self`/`cls`를 제외한 실제 호출 parameter를 object schema로 표현하며, required 여부는 Python default 유무를 따릅니다. 지원 타입은 primitive, enum, dataclass, `list[T]`, `tuple[...]`, `Mapping[str, T]`, `T | None`, `Union[...]`, `Annotated[T, ...]`입니다. `Any`, untyped parameter/return, untyped mapping, non-string mapping key, positional-only parameter, `*args`, `**kwargs`, JSON schema로 표현할 수 없는 임의 object는 definition/bootstrap 단계에서 `AgentDefinitionError`로 실패합니다.

`Annotated[T, SensitiveField(...)]`와 `Annotated[T, SecretField(...)]` metadata는 schema extraction 중 버리지 않고 `AgentToolSchemaHandle.input_sensitive_fields` / `output_sensitive_fields` descriptor에 보존합니다. 기본 `input_schema` / `output_schema`는 LLM-facing schema이므로 민감 extension을 포함하지 않습니다. 필요할 때만 `input_schema_for(ContextExposurePolicy(include_sensitive_schema_metadata=True))`처럼 명시 policy를 넘겨 `x-spakky-sensitive` extension을 포함한 schema copy를 얻습니다.

```python
from typing import Annotated

from spakky.agent import PII, SecretField, SensitiveField, agent_tool


@agent_tool(schema_name="customer.lookup")
async def lookup_customer(
    email: Annotated[str, SensitiveField(PII.EMAIL)],
    api_token: Annotated[str, SecretField()],
) -> dict[str, str]:
    ...
```

Model adapter가 decoded tool-call JSON을 받으면 tool 실행 전에 `descriptor.bind_invocation(payload)`로 Python signature binding을 수행합니다. Payload는 flat keyword object(`{"query": "agent", "limit": 5}`) 또는 structured object(`{"args": ["agent"], "kwargs": {"limit": 5}}`)를 사용할 수 있습니다. Binding은 `inspect.Signature`의 required/default/duplicate/unknown argument semantics를 따르며, 실패 시 tool callable을 실행하지 않고 `AgentToolBindingError`를 발생시킵니다.

`AgentToolDispatcher`는 이 조회·바인딩·실행을 하나의 building block으로 묶어, 소비자가 `if call.name == ...` 같은 이름 문자열 매칭 디스패치를 직접 작성하지 않도록 합니다. `AgentToolDispatcher(target=agent_instance, catalog=Agent.get(MyAgent).tool_catalog).dispatch(call)`은 `ModelToolCall.name`으로 descriptor를 조회하고, `bind_invocation`으로 `call.arguments`를 바인딩한 뒤, descriptor callable을 실행해 결과를 반환합니다. 동기/비동기 tool 모두를 처리하고, `self`/`cls` owner parameter가 없는 descriptor(MCP normalize 등 외부 도구)는 instance 없이 호출합니다. 카탈로그에 없는 이름은 `AgentToolDispatchError`로 실패합니다.

```python
from spakky.agent import Agent, AgentToolDispatcher

dispatcher = AgentToolDispatcher(
    target=assistant,
    catalog=Agent.get(CodeAssistant).tool_catalog,
)
result = await dispatcher.dispatch(model_tool_call)
```

## Delegation contract

Agent-to-agent delegation은 runtime topology나 자동 spawn 정책이 아니라 core building block으로 제공됩니다. Parent agent는 `DelegationPacket`으로 task, projected context slice, constraints, expected output, budget metadata, allowed capabilities, return policy를 명시하고, first-class target은 `AgentDelegateTarget`으로 식별되는 다른 `@Agent` component입니다.

`AgentExecutionSpec.teammates`는 이 계약을 model-callable synthetic tool로 노출합니다. Schema 이름은 `teammate.<schema_token(name)>.delegate`이며, teammate name은 소문자화하고 `[a-zA-Z0-9_]`가 아닌 문자를 `_`로 바꾼 schema-safe token으로 정규화됩니다. 입력은 `instruction`, 선택적 `task`, 선택적 `context_summary`입니다. 로컬 teammate(`AgentTeammate(pod=...)`)는 parent instance에 주입된 child Pod를 찾아 같은 process에서 `AgentRunner.run_events()`로 실행하고, child `AgentEvent`를 parent tool result 앞에 그대로 흘립니다. 원격 teammate(`card_url=...`)는 parent에 주입된 `IAgentDelegate` port를 사용하며, 공식 A2A 구현은 `spakky-a2a`의 `A2AAgentDelegate`입니다.

`IAgentDelegate`는 packet을 받아 `AgentYield[DelegationResult]` stream을 반환하는 execution hook입니다. Remote agent adapter, queue 기반 worker 같은 구체 topology는 이 hook 구현이 선택합니다. Child 결과는 `DelegationResult.to_parent_evidence()` 또는 `to_parent_yield()`로 `AgentEvidenceKind.DELEGATION` evidence와 기존 `AgentYieldKind.EVIDENCE` stream item에 연결할 수 있습니다. Raw child trace를 parent context에 강제로 주입하지 않고 summary/evidence reference 중심으로 되돌리는 ADR-0009 boundary를 유지합니다.

잘못된 signature나 지원하지 않는 metadata는 definition/bootstrap 단계에서 `AgentDefinitionError` 또는 `AgentBootstrapError`로 드러납니다.

## Tool metadata

`@agent_tool`은 method object에 descriptor metadata를 붙이고, `Agent` discovery는 owner, callable reference, schema handle, metadata를 deterministic catalog로 보존합니다. Core metadata의 정본은 permission/effects/idempotency/data access/externality/evidence capture이며, `ToolRisk`는 ADR-0009에 맞춰 이 정본 metadata에서 계산되는 derived contract입니다.

```python
from spakky.agent import (
    EvidenceCapture,
    Idempotency,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
)


@agent_tool(
    effects=ToolEffects.external_side_effect(),
    idempotency=Idempotency.NON_IDEMPOTENT,
    evidence=EvidenceCapture.SUMMARY,
    approval=ToolApprovalRequirement.DERIVED,
)
async def run_shell(command: str) -> dict[str, str]:
    ...
```

`descriptor.metadata.risk`는 read/write/side-effect/destructive/network 축을 typed enum으로 노출합니다. `descriptor.metadata.requires_approval_candidate`는 HITL 후보 여부를 계산하지만, `ToolApprovalRequirement.NOT_REQUIRED`를 명시한 tool까지 approval을 강제하지 않습니다. `descriptor.metadata.resume`은 완료된 action boundary를 재실행하지 않고, incomplete idempotent action은 retry 후보로, non-idempotent/unknown action은 approval 후보로 분류합니다.

`IAgentModel.stream()`은 model adapter가 message delta(`MESSAGE_DELTA`), reasoning delta(`REASONING_DELTA`), tool-call 경계(`TOOL_CALL_START`/`TOOL_CALL_END`)와 tool-call argument delta(`TOOL_CALL_ARGS_DELTA`), 그리고 기존 token delta, tool-call candidate, structured output, error, done을 `ModelStreamEventKind`로 구분해 내보내는 계약입니다. Reasoning을 지원하지 않는 backend는 `capability.supports_reasoning`이 `False`이며 `REASONING_DELTA` 이벤트를 에러 없이 생략합니다(graceful degrade) — 호출자는 `IAgentModel.capability`로 이를 run 이전에 판별합니다. 실제 vLLM/OpenAI-compatible HTTP 연결은 `plugins/spakky-vllm` 같은 outbound adapter가 담당하며, core package에는 production model implementation을 넣지 않습니다.

## CodeAssistant demo

`examples/code_assistant_demo.py`는 ADR-0009의 Claude Code-like 흐름을 프레임워크 building block 조합으로 보여주는 예제입니다. 완제품 coding app이 아니라 `@Agent CodeAssistant`가 constructor DI로 `IAgentModel`, workspace/shell/git ports, `IAgentStateRepository`, `IAgentSignalRepository`, `IAgentEvidenceRepository`를 받고, 외부 동작을 `@agent_tool`로 노출하는 방식을 검증합니다.

노출되는 tool schema는 `workspace.read`, `workspace.search`, `workspace.write`, `shell.command`, `git.status`, `git.diff`, `git.apply`입니다. 읽기 도구는 approval 없이 진행하고, workspace write/shell/git apply처럼 side effect가 있는 도구는 `plan_agent_tool_approval()`로 `AgentYieldKind.APPROVAL`을 먼저 내보냅니다. 실행 중 user message, approval decision, cancel signal은 repository에서 non-blocking으로 소비되며, action-boundary checkpoint evidence는 restart/resume 판단에 사용됩니다.

테스트는 scripted `IAgentModel`로 vLLM-compatible token/tool-call stream을 모사합니다. 실제 로컬 vLLM 연결은 core 예제가 아니라 `plugins/spakky-vllm`의 `VllmAgentModel`을 생성자에 주입해서 구성합니다. 운영 persistence fallback은 제공하지 않으며, durable 실행에는 SQLAlchemy contribution 같은 실제 repository provider가 필요합니다.

`examples/inbound_adapter_examples.py`는 `spakky-fastapi`의 `@ApiController`/`@websocket`과 `spakky-typer`의 `@CliController`/`@command`로 `CodeAssistant.execute()` stream을 노출하는 app-level wiring을 보여줍니다. 두 adapter 모두 container에서 `CodeAssistant`를 UseCase처럼 resolve하고 `AgentYield`를 transport event로 변환하며, approval/user input은 `IAgentSignalRepository.append()`로 추가합니다. 이 예제는 기존 plugin building block 조합이며 `spakky-agent-fastapi`나 `spakky-agent-typer` 패키지를 만들지 않습니다.

## Context contract

Model input context는 raw 문자열을 이어 붙인 prompt snapshot이 아니라 `ContextPack` sequence로 전달합니다. 각 pack은 source, role, freshness, relevance, token budget, sensitivity metadata를 보존하고, `ContextManifest`는 pack 구성과 origin/evidence reference를 audit 단위로 남깁니다. 압축이나 요약은 원본 evidence를 대체하지 않고 `ContextDigest` derived evidence로 표현합니다.

`ModelRequest.assemble_messages()`는 기존 `messages`와 `context` packs를 provider-neutral `ModelMessage` tuple로 조립하는 hook입니다. 이 hook은 `ContextPack.sensitive_fields`와 `ContextSensitivity.REDACTED`를 먼저 guard하므로 secret 값이 model input content에 원문으로 들어가지 않습니다. Adapter는 이 hook을 사용해 context metadata를 잃지 않고 provider payload로 변환할 수 있습니다.

Context rot은 prompt injection detector가 아니라 quality/budget metadata입니다. `ContextHealthSignal`은 `stale`, `contradictory`, `low_relevance`, `over_budget`, `polluted` 증상을 pack/manifest/evidence reference와 함께 표현하고, `IAgentContextHandler`는 이 signal에서 `ContextOptimizationAction`을 선택합니다. Action kind는 `compression`, `retrieval_refresh`, `delegation`, `context_slice_drop`입니다.

Optimization 실행 전후 기록은 기존 `AgentYieldKind.EVIDENCE` stream과 append-only `AgentEvidenceKind.CONTEXT_OPTIMIZATION` evidence로 남깁니다. 압축은 원본 evidence를 수정하지 않고 `ContextDigest` 또는 derived evidence reference를 추가하는 방식으로만 표현합니다.

Evidence와 model output/stream boundary도 같은 descriptor를 재사용합니다. `AgentEvidenceCandidate.tool_result(..., sensitive_fields=...)`, `ModelResponse.guarded(...)`, `ModelStreamEvent.guarded(...)`는 raw PII/secret 값을 append-only evidence나 downstream stream payload에 넣기 전에 deterministic replacement로 바꿉니다.

Streaming output은 `StreamingRedactionSession`으로 bounded buffering을 적용할 수 있습니다. Adapter나 agent orchestration은 `StreamingSensitivePattern`을 제공하고 `StreamingRedactionPolicy(buffer_size=..., emit_chunk_size=...)`로 redaction correctness와 latency tradeoff를 조절합니다. Session은 `push()`에서 안전하게 확정된 prefix만 반환하고 `finish()`에서 aggregate final audit을 항상 실행합니다. Audit이 raw 후보를 발견하면 기본값은 `AgentOutputGuardError` raise이며, `StreamingGuardFailureMode.EMIT_ERROR`를 선택한 경우에는 stream consumer가 `StreamingRedactionAudit.to_evidence_payload()`와 error payload를 append-only evidence / `AgentYieldKind.ERROR`로 남길 수 있습니다. Core는 heuristic PII detector를 내장하지 않으며, detector나 concrete pattern selection은 extension/adapter가 담당합니다.
