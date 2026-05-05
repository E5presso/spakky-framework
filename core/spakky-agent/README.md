# spakky-agent

`spakky-agent`는 ADR-0009 Agentic Hexagonal Architecture의 core contract 패키지입니다. Agent를 LLM SDK wrapper가 아니라 `@UseCase`와 같은 application workflow component로 다루기 위한 public 타입 표면을 제공합니다.

## 언제 필요한가

- agentic workflow를 Spakky DI/hexagonal architecture 안에서 표현하려는 경우
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

- `Agent`, `AgentExecutionSpec`, `AgentExecutionLimits`: `@UseCase`와 동격인 Pod stereotype과 보조 실행 의미
- `AgentYield`: `execute()`가 caller에게 흘려보내는 typed stream item
- `AgentState`: long-running agent execution의 materialized lifecycle state
- `AgentSignal`: 실행 중 들어오는 user message, approval, cancel 같은 inbound stimulus
- `AgentSignalPollPoint`, `consume_pending_agent_signals`: safe boundary나 configured poll point에서 durable signal queue를 대기 없이 소비하는 helper
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
- `IAgentModel`: vLLM 등 model backend가 구현하는 outbound port
- `ModelRequest`, `ModelResponse`, `ModelStreamEvent`: provider-neutral model 호출/응답/stream 계약
- `ToolCallingSpec`, `ModelToolSpec`, `ModelToolCall`: model-facing tool call 요청과 후보 결과
- `agent_tool`, `AgentToolBoundInvocation`, `AgentToolBindingError`, `ToolEffects`, `ToolRisk`, `ToolApprovalRequirement`, `ToolResumeMetadata`, `EvidenceCapture`: tool binding, risk, approval, idempotency, evidence capture metadata

## 의존성 경계

Core package는 `spakky` core에만 의존합니다. vLLM, SQLAlchemy, FastAPI, Typer 같은 infrastructure dependency를 직접 import하지 않습니다.

Production persistence fallback도 제공하지 않습니다. State, signal, evidence repository 구현은 SQLAlchemy 등 provider plugin의 feature contribution으로 등록되어야 하며, 누락 시 bootstrap 단계에서 custom error로 실패해야 합니다.

Durable 실행 경로는 `AgentExecutionSpec.recovery == RecoveryStrategy.ACTION_BOUNDARY` 또는 `accepted_signals` 선언에서 파생됩니다. 이 경우 bootstrap은 `IAgentStateRepository`, `IAgentSignalRepository`, `IAgentEvidenceRepository`가 모두 등록되어 있는지 검증하고, 누락 시 필요한 repository type과 설치해야 할 `spakky-sqlalchemy[agent]` / `spakky.contributions.spakky.agent` provider contribution을 error message에 포함합니다. 운영용 in-memory repository fallback은 없습니다.

`AgentEvidenceRepository`의 agent-facing interface는 append/read 계열만 노출합니다. Redaction, correction, context digest 갱신은 기존 evidence를 수정하지 않고 새 evidence를 append하는 방식으로 표현합니다.

## 사용 예시

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

`@Agent`는 `@Pod` 계열 stereotype이므로 application scan과 constructor DI에 참여합니다. `execute()`는 `Generator[AgentYield[T], None, None]` 또는 `AsyncGenerator[AgentYield[T], None]`로 typed stream item을 yield할 수 있고, non-generator 반환형은 streaming 없는 직접 결과 계약으로 취급됩니다. Inbound adapter가 SSE/WebSocket/CLI처럼 진행 상태를 즉시 내보내야 한다면 `AgentYield` generator 계약을 사용해야 합니다.

`AgentYieldKind`의 public status vocabulary는 `token`, `progress`, `tool`, `evidence`, `approval`, `final`, `error`, `cancel`입니다. 각 item의 payload는 `Token`, `Progress`, `Tool`, `Evidence`, `Approval`, `Final[T]`, `Error`, `Cancel` value object로 구분되므로 inbound adapter는 별도 stream projector 없이 generator를 직접 순회해 transport별 이벤트로 바꿀 수 있습니다.

HITL approval은 모든 action 앞에 자동 삽입되는 step이 아니라 risk boundary에서만 materialize됩니다. `plan_agent_tool_approval()`은 `@agent_tool` descriptor의 `ToolRisk`와 `ToolApprovalRequirement`를 읽어 low-risk 또는 `NOT_REQUIRED` tool은 `PROCEED`로 돌려보내고, side-effect/write/network/destructive 후보만 `AgentState(status=INTERRUPTED, transition=WAITING_APPROVAL, reason=APPROVAL_REQUIRED)`와 `AgentYieldKind.APPROVAL` item으로 바꿉니다. Inbound adapter가 approval decision signal을 append하면 `parse_agent_approval_decision_signal()`이 `approve`, `reject`, `modify`, `defer`, `cancel`을 typed outcome으로 해석합니다. `approve`/`modify`는 `ACTIVE/RUNNING`, `defer`는 계속 `INTERRUPTED/WAITING_APPROVAL`, `reject`는 `FAILED`, `cancel`은 `CANCELLING`으로 분리되므로 approval wait와 cancellation/failure lifecycle이 섞이지 않습니다.

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

## Delegation contract

Agent-to-agent delegation은 runtime topology나 자동 spawn 정책이 아니라 core building block으로 제공됩니다. Parent agent는 `DelegationPacket`으로 task, projected context slice, constraints, expected output, budget metadata, allowed capabilities, return policy를 명시하고, first-class target은 `AgentDelegateTarget`으로 식별되는 다른 `@Agent` component입니다.

`IAgentDelegate`는 packet을 받아 `AgentYield[DelegationResult]` stream을 반환하는 execution hook입니다. Local component 호출, remote agent adapter, queue 기반 worker 같은 구체 topology는 이 hook 구현이 선택합니다. Child 결과는 `DelegationResult.to_parent_evidence()` 또는 `to_parent_yield()`로 `AgentEvidenceKind.DELEGATION` evidence와 기존 `AgentYieldKind.EVIDENCE` stream item에 연결할 수 있습니다. Raw child trace를 parent context에 강제로 주입하지 않고 summary/evidence reference 중심으로 되돌리는 ADR-0009 boundary를 유지합니다.

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

`IAgentModel.stream()`은 model adapter가 token delta, tool-call candidate, structured output, error, done을 `ModelStreamEventKind`로 구분해 내보내는 계약입니다. 실제 vLLM/OpenAI-compatible HTTP 연결은 `plugins/spakky-vllm` 같은 outbound adapter가 담당하며, core package에는 production model implementation을 넣지 않습니다.

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
