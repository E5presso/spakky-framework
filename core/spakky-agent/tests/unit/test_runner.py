"""Tests for the framework-owned AgentRunner execution loop."""

from asyncio import Event
from collections.abc import AsyncGenerator, AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, replace
from time import sleep
from typing import TypedDict, cast, override

import pytest
from pydantic import BaseModel
import spakky.agent.runner as runner_module

from spakky.agent import (
    Agent,
    AgentContext,
    AgentApprovalPlan,
    AgentApprovalPlanAction,
    AgentEvidenceKind,
    AgentExecutionLimits,
    AgentExecutionSpec,
    AgentTeammate,
    AgentRunner,
    AgentSignal,
    AgentSignalKind,
    AgentState,
    AgentStateReason,
    AgentStateTransition,
    AgentStatus,
    AgentToolApprovalContext,
    AgentToolDescriptor,
    AgentYield,
    AgentYieldKind,
    Approval,
    ArtifactEvent,
    Cancel,
    ConversationTurn,
    ContextDigest,
    ContextFreshness,
    ContextManifest,
    ContextManifestEntry,
    ContextPack,
    ContextPackRole,
    ContextSensitivity,
    ContextTokenBudget,
    Error,
    EvidenceCapture,
    Final,
    IAgentContextProvider,
    IAgentModel,
    ICompactionStrategy,
    Idempotency,
    ITaskStore,
    JsonObject,
    JsonValue,
    AgentCompactionPolicy,
    KeepRecentMessagesCompactionStrategy,
    SummarizeOldTurnsCompactionStrategy,
    TrimToolResultsCompactionStrategy,
    ModelCapability,
    ModelError,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelSelection,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    ModelUsage,
    Progress,
    RecoveryStrategy,
    SecretField,
    SensitiveFieldDescriptor,
    StreamingExposureMode,
    Token,
    TimeoutPolicy,
    Tool,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
    on_signal,
)
from spakky.agent.error import (
    AgentDefinitionError,
    AgentModelConfigurationError,
    AgentPersistenceConfigurationError,
    AgentToolDispatchError,
)
from spakky.agent.event import (
    AgentEvent,
    AgentEventAttribution,
    AgentEventKind,
    MessageDeltaEvent,
    ReasoningDeltaEvent,
    RunFinishedEvent,
    RunPausedEvent,
    RunStartedEvent,
    StepFinishedEvent,
    StepStartedEvent,
    ToolCallArgsDeltaEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from spakky.agent.inbound import RunAgentInput
from spakky.agent.runner import (
    RUNNER_CHECKPOINT_METADATA_KEY,
    _arguments_digest,
    _history_with_approved_call,
)
from tests.unit.test_event import _to_a2a, _to_ag_ui
from tests.unit.test_code_assistant_demo import (
    FakeEvidenceRepository,
    FakeSignalRepository,
    FakeStateRepository,
    RecordingModel,
)

DURABLE_SPEC = AgentExecutionSpec(
    name="runner_probe",
    accepted_signals=(
        AgentSignalKind.USER_MESSAGE,
        AgentSignalKind.APPROVAL_DECISION,
        AgentSignalKind.CANCEL,
        AgentSignalKind.RESUME,
    ),
    recovery=RecoveryStrategy.ACTION_BOUNDARY,
)


class EchoResult(BaseModel):
    """Pydantic tool result used to prove neutral serialization."""

    value: str


@dataclass(frozen=True, slots=True)
class EchoRecord:
    """Dataclass tool result used to prove neutral serialization."""

    value: str


@Agent(spec=DURABLE_SPEC)
class ProbeAgent:
    """Durable probe agent exercising the framework-owned loop end to end."""

    def __init__(
        self,
        model: IAgentModel,
        states: FakeStateRepository,
        signals: FakeSignalRepository,
        evidence: FakeEvidenceRepository,
    ) -> None:
        self._model = model
        self._states = states
        self._signals = signals
        self._evidence = evidence

    @agent_tool(
        schema_name="echo.read",
        description="Read echo without approval.",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def echo_read(self, value: str) -> EchoRecord:
        """Echo a value back as a structured result."""
        return EchoRecord(value=value)

    @agent_tool(
        schema_name="echo.write",
        description="Write echo requiring approval.",
        effects=ToolEffects.write_state(),
        idempotency=Idempotency.CONDITIONALLY_IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.REQUIRED,
    )
    def echo_write(self, value: str) -> EchoRecord:
        """Echo a value back after approval."""
        return EchoRecord(value=value)


@Agent(spec=AgentExecutionSpec(name="stateless_probe"))
class StatelessProbeAgent:
    """Stateless probe agent that runs model to final without durability."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model

    @agent_tool(
        schema_name="echo.read",
        description="Read echo without approval.",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def echo_read(self, value: str) -> EchoRecord:
        """Echo a value back as a structured result."""
        return EchoRecord(value=value)


@Agent(spec=AgentExecutionSpec(name="researcher"))
class ResearcherAgent:
    """Local teammate fixture used by delegation tool wiring tests."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model


@Agent(
    spec=AgentExecutionSpec(
        name="orchestrator",
        teammates=(AgentTeammate(name="researcher", pod=ResearcherAgent),),
    )
)
class OrchestratorAgent:
    """Parent agent with a local teammate declared in its execution spec."""

    def __init__(self, model: IAgentModel, researcher: ResearcherAgent) -> None:
        self._model = model
        self._researcher = researcher


@Agent(spec=AgentExecutionSpec(name="toolless_probe"))
class ToollessProbeAgent:
    """Stateless agent with no tools to prove tool_calling stays absent."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model


class ScriptedRoundModel(IAgentModel):
    """Model whose consecutive requests consume explicit stream rounds."""

    def __init__(self, rounds: Sequence[Sequence[ModelStreamEvent]]) -> None:
        self._rounds = tuple(tuple(round_) for round_ in rounds)
        self.requests: list[ModelRequest] = []

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        raise AgentDefinitionError("Scripted stream model does not complete")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        index = len(self.requests)
        self.requests.append(request)
        round_ = self._rounds[index] if index < len(self._rounds) else ()
        for event in round_:
            yield event


class ScriptedCompleteModel(IAgentModel):
    """Non-stream model whose responses drive guarded iterative execution."""

    def __init__(self, responses: Sequence[ModelResponse]) -> None:
        self._responses = tuple(responses)
        self.requests: list[ModelRequest] = []
        self.stream_calls = 0

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        index = len(self.requests)
        self.requests.append(request)
        return self._responses[index]

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        self.stream_calls += 1
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


class StructuredRoundModel(ScriptedRoundModel):
    """Scripted stream model advertising structured-output support."""

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability(supports_structured_output=True, supports_tools=True)


class StructuredCompleteModel(ScriptedCompleteModel):
    """Scripted complete model advertising structured-output support."""

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability(supports_structured_output=True, supports_tools=True)


class EchoTypedDict(TypedDict):
    """TypedDict structured final fixture."""

    value: str


class HangingModel(IAgentModel):
    """Model that never produces its first stream item."""

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        await Event().wait()
        return ModelResponse(content="unreachable")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        await Event().wait()
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


class FrameworkFailingModel(IAgentModel):
    """Model port raising a typed framework failure from both SDK surfaces."""

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        raise AgentDefinitionError("framework complete failure")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        raise AgentDefinitionError("framework stream failure")
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


class CrashThenDoneModel(IAgentModel):
    """Unexpected first model crash followed by a successful same-step retry."""

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="unused")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        if len(self.requests) == 1:
            raise RuntimeError("simulated model crash")
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


class RecordingContextProvider(IAgentContextProvider):
    """Context provider recording 1-based model-step requests."""

    def __init__(
        self,
        contexts: Sequence[AgentContext],
        *,
        error: Exception | None = None,
        hang: bool = False,
        sequential: bool = False,
    ) -> None:
        self._contexts = tuple(contexts)
        self._error = error
        self._hang = hang
        self._sequential = sequential
        self.calls: list[int] = []

    @override
    async def provide(
        self,
        run_input: RunAgentInput,
        model_step: int,
    ) -> AgentContext:
        self.calls.append(model_step)
        if self._hang:
            await Event().wait()
        if self._error is not None:
            raise self._error
        requested_index = len(self.calls) - 1 if self._sequential else model_step - 1
        index = min(requested_index, len(self._contexts) - 1)
        return self._contexts[index]


class _EchoToolAgentBase:
    """Undecorated reusable echo tool surface for limits-mode agents."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model

    @agent_tool(
        schema_name="echo.read",
        effects=ToolEffects.read_only(),
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def echo_read(self, value: str) -> EchoRecord:
        return EchoRecord(value=value)


class _ModelOnlyAgentBase:
    """Undecorated model-only constructor shared by limit fixtures."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model


@Agent(
    spec=AgentExecutionSpec(
        name="structured_output_probe",
        output_type=EchoResult,
    )
)
class StructuredOutputProbeAgent(_ModelOnlyAgentBase):
    """Streaming structured-output target without tools."""


@Agent(
    spec=AgentExecutionSpec(
        name="structured_complete_probe",
        output_type=EchoResult,
        streaming_exposure_mode=StreamingExposureMode.NO_STREAM_UNTIL_FINAL_GUARDED,
    )
)
class StructuredCompleteProbeAgent(_ModelOnlyAgentBase):
    """Complete-path structured-output target without tools."""


@Agent(
    spec=AgentExecutionSpec(
        name="structured_tool_probe",
        output_type=EchoResult,
    )
)
class StructuredToolProbeAgent(_EchoToolAgentBase):
    """Structured-output target used for tool ambiguity failures."""


@Agent(
    spec=AgentExecutionSpec(
        name="structured_complete_tool_probe",
        output_type=EchoResult,
        streaming_exposure_mode=StreamingExposureMode.NO_STREAM_UNTIL_FINAL_GUARDED,
    )
)
class StructuredCompleteToolProbeAgent(_EchoToolAgentBase):
    """Complete-path structured/tool ambiguity target."""


@Agent(
    spec=AgentExecutionSpec(
        name="guarded_complete_probe",
        streaming_exposure_mode=StreamingExposureMode.NO_STREAM_UNTIL_FINAL_GUARDED,
    )
)
class GuardedCompleteProbeAgent(_EchoToolAgentBase):
    """Stateless tool agent forcing the non-stream complete model path."""


@Agent(
    spec=AgentExecutionSpec(
        name="step_limited_probe",
        limits=AgentExecutionLimits(max_steps=2),
    )
)
class StepLimitedProbeAgent(_EchoToolAgentBase):
    """Stateless tool agent with two allowed model iterations."""


@Agent(
    spec=AgentExecutionSpec(
        name="tool_limited_probe",
        limits=AgentExecutionLimits(max_tool_calls=1),
    )
)
class ToolLimitedProbeAgent(_EchoToolAgentBase):
    """Stateless tool agent allowing only one actual dispatch."""


@Agent(
    spec=AgentExecutionSpec(
        name="token_limited_probe",
        limits=AgentExecutionLimits(max_tokens=5),
    )
)
class TokenLimitedProbeAgent(_ModelOnlyAgentBase):
    """Stateless model agent requiring reliable cumulative usage."""


@Agent(
    spec=AgentExecutionSpec(
        name="durable_token_limited_probe",
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
        limits=AgentExecutionLimits(max_tokens=5),
    )
)
class DurableTokenLimitedProbeAgent:
    """Durable token-limit target for routing/evidence terminal assertions."""

    def __init__(
        self,
        model: IAgentModel,
        states: FakeStateRepository,
        signals: FakeSignalRepository,
        evidence: FakeEvidenceRepository,
    ) -> None:
        self._model = model
        self._states = states
        self._signals = signals
        self._evidence = evidence


class _ContextProbeBase:
    """Shared durable context-provider target with one continuation tool."""

    def __init__(
        self,
        model: IAgentModel,
        provider: IAgentContextProvider,
        states: FakeStateRepository,
        signals: FakeSignalRepository,
        evidence: FakeEvidenceRepository,
    ) -> None:
        self._model = model
        self._provider = provider
        self._states = states
        self._signals = signals
        self._evidence = evidence

    @agent_tool(
        schema_name="context.echo",
        effects=ToolEffects.read_only(),
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def context_echo(self, value: str) -> str:
        return value

    @agent_tool(
        schema_name="context.write",
        effects=ToolEffects.write_state(),
        idempotency=Idempotency.CONDITIONALLY_IDEMPOTENT,
        approval=ToolApprovalRequirement.REQUIRED,
    )
    def context_write(self, value: str) -> str:
        return value


@Agent(
    spec=AgentExecutionSpec(
        name="context_probe",
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
    )
)
class ContextProbeAgent(_ContextProbeBase):
    """Caches dynamic context after its first model step."""


@Agent(
    spec=AgentExecutionSpec(
        name="refreshing_context_probe",
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
        refresh_context_each_step=True,
    )
)
class RefreshingContextProbeAgent(_ContextProbeBase):
    """Refreshes dynamic context for every model step."""


@Agent(
    spec=AgentExecutionSpec(
        name="timeout_context_probe",
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
        limits=AgentExecutionLimits(timeout_seconds=0.05),
    )
)
class TimeoutContextProbeAgent(_ContextProbeBase):
    """Enforces the run deadline around a hanging context provider."""


@Agent(
    spec=AgentExecutionSpec(
        name="timeout_probe",
        limits=AgentExecutionLimits(timeout_seconds=0.05),
    )
)
class TimeoutProbeAgent(_ModelOnlyAgentBase):
    """Stateless agent enforcing a model wall-clock deadline."""


@Agent(
    spec=AgentExecutionSpec(
        name="durable_timeout_probe",
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
        limits=AgentExecutionLimits(timeout_seconds=0.05),
    )
)
class DurableTimeoutProbeAgent:
    """Durable agent with a hanging async tool."""

    def __init__(
        self,
        model: IAgentModel,
        states: FakeStateRepository,
        signals: FakeSignalRepository,
        evidence: FakeEvidenceRepository,
    ) -> None:
        self._model = model
        self._states = states
        self._signals = signals
        self._evidence = evidence

    @agent_tool(
        schema_name="wait.forever",
        effects=ToolEffects.read_only(),
        timeout=TimeoutPolicy(seconds=0.2),
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    async def wait_forever(self) -> str:
        await Event().wait()
        return "unreachable"


@Agent(
    spec=AgentExecutionSpec(
        name="sync_timeout_probe",
        limits=AgentExecutionLimits(timeout_seconds=0.05),
    )
)
class SyncTimeoutProbeAgent:
    """Sync tool target proving an active deadline fails before invocation."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model
        self.called = False

    @agent_tool(
        schema_name="sync.sleep",
        effects=ToolEffects.read_only(),
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def sleep_sync(self) -> str:
        sleep(0.2)
        self.called = True
        return "slept"


@Agent(
    spec=AgentExecutionSpec(
        name="durable_guarded_framework_probe",
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
        streaming_exposure_mode=StreamingExposureMode.NO_STREAM_UNTIL_FINAL_GUARDED,
    )
)
class DurableGuardedFrameworkProbeAgent:
    """Durable guarded model target for complete() terminal normalization."""

    def __init__(
        self,
        model: IAgentModel,
        states: FakeStateRepository,
        signals: FakeSignalRepository,
        evidence: FakeEvidenceRepository,
    ) -> None:
        self._model = model
        self._states = states
        self._signals = signals
        self._evidence = evidence


@Agent(
    spec=AgentExecutionSpec(
        name="framework_failing_tool_probe",
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
    )
)
class FrameworkFailingToolProbeAgent:
    """Durable tool target raising or returning a non-JSON framework result."""

    def __init__(
        self,
        model: IAgentModel,
        states: FakeStateRepository,
        signals: FakeSignalRepository,
        evidence: FakeEvidenceRepository,
    ) -> None:
        self._model = model
        self._states = states
        self._signals = signals
        self._evidence = evidence

    @agent_tool(
        schema_name="framework.raise",
        effects=ToolEffects.read_only(),
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def raise_framework(self) -> str:
        raise AgentDefinitionError("tool framework failure")

    @agent_tool(
        schema_name="framework.bad_result",
        effects=ToolEffects.read_only(),
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def bad_result(self) -> str:
        return cast(str, {"not-json"})


@Agent(
    spec=AgentExecutionSpec(
        name="unsupported_signal_projection_probe",
        accepted_signals=(AgentSignalKind.STEERING_INSTRUCTION,),
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
    )
)
class UnsupportedSignalProjectionProbeAgent:
    """Signal hook intentionally yielding a non-projectable public token."""

    def __init__(
        self,
        model: IAgentModel,
        states: FakeStateRepository,
        signals: FakeSignalRepository,
        evidence: FakeEvidenceRepository,
    ) -> None:
        self._model = model
        self._states = states
        self._signals = signals
        self._evidence = evidence

    @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
    async def on_steering(
        self,
        signal: AgentSignal,
    ) -> AsyncGenerator[AgentYield[object], None]:
        yield AgentYield(
            kind=AgentYieldKind.TOKEN,
            payload=Token(
                "unsupported signal token", metadata={"signal_id": signal.id}
            ),
        )

    @agent_tool(
        schema_name="unsupported.signal_after",
        effects=ToolEffects.read_only(),
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def signal_after(self, state_id: str) -> str:
        self._signals.append(
            AgentSignal(
                id=f"steer:{state_id}",
                agent_state_id=state_id,
                kind=AgentSignalKind.STEERING_INSTRUCTION,
                payload={"instruction": "token"},
            )
        )
        return "queued"


@Agent(spec=AgentExecutionSpec(name="batch_probe"))
class BatchProbeAgent:
    """Stateful test target proving invalid batches dispatch no prefix calls."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model
        self.dispatched: list[str] = []

    @agent_tool(
        schema_name="batch.record",
        effects=ToolEffects.read_only(),
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def record(self, value: str) -> str:
        self.dispatched.append(value)
        return value


@Agent(
    spec=AgentExecutionSpec(
        name="non_idempotent_crash_probe",
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
    )
)
class NonIdempotentCrashProbeAgent:
    """Durable non-idempotent tool target for incomplete-boundary restart tests."""

    def __init__(
        self,
        model: IAgentModel,
        states: FakeStateRepository,
        signals: FakeSignalRepository,
        evidence: FakeEvidenceRepository,
    ) -> None:
        self._model = model
        self._states = states
        self._signals = signals
        self._evidence = evidence
        self.dispatched = 0

    @agent_tool(
        schema_name="external.write",
        effects=ToolEffects.external_side_effect(),
        idempotency=Idempotency.NON_IDEMPOTENT,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def external_write(self, value: str) -> str:
        self.dispatched += 1
        return value


@Agent(
    spec=AgentExecutionSpec(
        name="cancel_during_tool_probe",
        accepted_signals=(AgentSignalKind.CANCEL,),
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
    )
)
class CancelDuringToolProbeAgent:
    """Tool target that queues cancellation before returning its result."""

    def __init__(
        self,
        model: IAgentModel,
        states: FakeStateRepository,
        signals: FakeSignalRepository,
        evidence: FakeEvidenceRepository,
    ) -> None:
        self._model = model
        self._states = states
        self._signals = signals
        self._evidence = evidence

    @agent_tool(
        schema_name="cancel.after",
        effects=ToolEffects.read_only(),
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def cancel_after(self) -> str:
        self._signals.append(
            AgentSignal(
                id="cancel:during-tool",
                agent_state_id="cancel-tool",
                kind=AgentSignalKind.CANCEL,
                payload={
                    "reason": "cancel after dispatch",
                    "requested_by": "tester",
                },
            )
        )
        return "cancelled"


@Agent(
    spec=AgentExecutionSpec(
        name="signal_during_tool_probe",
        accepted_signals=(AgentSignalKind.USER_MESSAGE,),
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
    )
)
class SignalDuringToolProbeAgent:
    """Tool fixture queues a non-terminal signal at the post-dispatch boundary."""

    def __init__(
        self,
        model: IAgentModel,
        states: FakeStateRepository,
        signals: FakeSignalRepository,
        evidence: FakeEvidenceRepository,
    ) -> None:
        self._model = model
        self._states = states
        self._signals = signals
        self._evidence = evidence

    @agent_tool(
        schema_name="signal.after",
        effects=ToolEffects.read_only(),
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def signal_after(self, state_id: str) -> str:
        self._signals.append(
            AgentSignal(
                id=f"user:{state_id}",
                agent_state_id=state_id,
                kind=AgentSignalKind.USER_MESSAGE,
                payload={"message": "after tool"},
            )
        )
        return "signalled"


@Agent(
    spec=AgentExecutionSpec(
        name="lifecycle_mutating_tool_probe",
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
    )
)
class LifecycleMutatingToolProbeAgent:
    """Tool fixture simulating an external lifecycle failure during dispatch."""

    def __init__(
        self,
        model: IAgentModel,
        states: FakeStateRepository,
        signals: FakeSignalRepository,
        evidence: FakeEvidenceRepository,
    ) -> None:
        self._model = model
        self._states = states
        self._signals = signals
        self._evidence = evidence

    @agent_tool(
        schema_name="lifecycle.fail",
        effects=ToolEffects.read_only(),
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def fail_state(self, state_id: str) -> str:
        current = self._states.get(state_id)
        self._states.save(
            replace(
                current,
                status=AgentStatus.FAILED,
                transition=AgentStateTransition.FAILED,
                reason=AgentStateReason.EXECUTION_FAILED,
                current_activity="external lifecycle failure",
            )
        )
        return "failed"


@Agent(spec=AgentExecutionSpec(name="tool_policy_timeout_probe"))
class ToolPolicyTimeoutProbeAgent(_ModelOnlyAgentBase):
    """Stateless agent whose tool-specific timeout is the only deadline."""

    @agent_tool(
        schema_name="wait.policy",
        effects=ToolEffects.read_only(),
        timeout=TimeoutPolicy(seconds=0.05),
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    async def wait_policy(self) -> str:
        await Event().wait()
        return "unreachable"


def _invoke_execute(
    agent: object,
    run_input: RunAgentInput,
) -> AsyncIterator[AgentYield[object]]:
    """Invoke an agent's framework-provided execute() without static binding.

    The synthesized execute() is bound onto the class at decoration time, so it
    is read from the class namespace (``vars``) rather than as a statically known
    attribute, then called with the instance as the bound ``self``.
    """
    execute = vars(type(agent))["execute"]
    return execute(agent, run_input)


async def _collect(
    stream: AsyncIterator[AgentYield[object]],
) -> tuple[AgentYield[object], ...]:
    items: list[AgentYield[object]] = []
    async for item in stream:
        items.append(item)
    return tuple(items)


async def _run_durable(
    model: IAgentModel,
    command: RunAgentInput,
    states: FakeStateRepository,
    signals: FakeSignalRepository,
    evidence: FakeEvidenceRepository,
) -> tuple[AgentYield[object], ...]:
    agent = ProbeAgent(model, states, signals, evidence)
    return await _collect(_invoke_execute(agent, command))


def _tool_event(
    name: str, arguments: dict[str, JsonValue], call_id: str
) -> ModelStreamEvent:
    return ModelStreamEvent(
        kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
        tool_call=ModelToolCall(name=name, arguments=arguments, call_id=call_id),
    )


def _approval_signal(state_id: str, request_id: str, decision: str):

    return AgentSignal(
        id=request_id,
        agent_state_id=state_id,
        kind=AgentSignalKind.APPROVAL_DECISION,
        payload={"request_id": request_id, "decision": decision},
    )


def _approval_request_id(
    state_id: str,
    call_id: str,
    arguments: JsonObject,
) -> str:

    return f"approval:{state_id}:{call_id}:{_arguments_digest(arguments)}"


async def test_agent_runner_expect_auto_provided_execute_runs_tools_and_final() -> None:
    """spec과 @agent_tool만 선언한 Agent가 도구 호출과 종료까지 자동 실행된다."""
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.TOKEN_DELTA,
                token_delta="planning",
            ),
            _tool_event("echo.read", {"value": "hi"}, "read-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="echo"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    kinds = {item.kind for item in items}
    assert {
        AgentYieldKind.TOKEN,
        AgentYieldKind.TOOL,
        AgentYieldKind.EVIDENCE,
        AgentYieldKind.FINAL,
    } <= kinds
    assert states.get("run-1").status is AgentStatus.COMPLETED


async def test_agent_runner_expect_approval_pause_then_signal_resume_dispatches() -> (
    None
):
    """승인 필요 도구가 pause 후 승인 signal 수신으로 resume되어 디스패치된다."""
    model = RecordingModel(
        (
            _tool_event("echo.write", {"value": "draft"}, "write-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()
    evidence = FakeEvidenceRepository()
    signals = FakeSignalRepository(
        (
            _approval_signal(
                "run-1",
                _approval_request_id("run-1", "write-1", {"value": "draft"}),
                "approve",
            ),
        )
    )

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="write"),
        states,
        signals,
        evidence,
    )

    assert any(isinstance(item.payload, Approval) for item in items)
    assert any(isinstance(item.payload, Tool) for item in items)
    assert AgentEvidenceKind.APPROVAL in {
        artifact.kind for artifact in evidence.list_by_state("run-1")
    }
    assert states.get("run-1").status is AgentStatus.COMPLETED


async def test_agent_runner_expect_approval_skips_unrelated_and_mismatched_signals() -> (
    None
):
    """승인 대기 큐의 무관 signal과 다른 request_id 결정은 건너뛰고 일치 결정만 쓴다."""

    model = RecordingModel(
        (
            _tool_event("echo.write", {"value": "draft"}, "write-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()
    signals = FakeSignalRepository(
        (
            AgentSignal(
                id="resume:run-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.RESUME,
                payload={},
            ),
            _approval_signal("run-1", "approval:run-1:other.tool", "approve"),
            _approval_signal(
                "run-1",
                _approval_request_id("run-1", "write-1", {"value": "draft"}),
                "approve",
            ),
        )
    )

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="write"),
        states,
        signals,
        FakeEvidenceRepository(),
    )

    assert any(isinstance(item.payload, Tool) for item in items)
    assert states.get("run-1").status is AgentStatus.COMPLETED


async def test_agent_runner_expect_cancel_without_requested_by_omits_attribution() -> (
    None
):
    """requested_by가 없는 cancel signal은 Cancel.requested_by를 None으로 둔다."""

    states = FakeStateRepository()
    signals = FakeSignalRepository(
        (
            AgentSignal(
                id="cancel:run-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.CANCEL,
                payload={"reason": "stop"},
            ),
        )
    )

    items = await _run_durable(
        RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),)),
        RunAgentInput(state_id="run-1", instruction="cancel"),
        states,
        signals,
        FakeEvidenceRepository(),
    )

    cancel = items[0].payload
    assert isinstance(cancel, Cancel)
    assert cancel.requested_by is None


async def test_agent_runner_expect_approval_reject_stops_without_final() -> None:
    """승인 거부 결정은 도구 디스패치 없이 FINAL 없이 종료한다."""
    model = RecordingModel(
        (
            _tool_event("echo.write", {"value": "draft"}, "write-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()
    signals = FakeSignalRepository(
        (
            _approval_signal(
                "run-1",
                _approval_request_id("run-1", "write-1", {"value": "draft"}),
                "reject",
            ),
        )
    )

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="write"),
        states,
        signals,
        FakeEvidenceRepository(),
    )

    assert not any(item.kind is AgentYieldKind.FINAL for item in items)
    assert not any(isinstance(item.payload, Tool) for item in items)
    assert states.get("run-1").status is AgentStatus.FAILED


async def test_agent_runner_expect_no_pending_decision_pauses_without_dispatch() -> (
    None
):
    """승인 결정 signal이 없으면 paused 상태에서 도구를 디스패치하지 않는다."""
    model = RecordingModel(
        (
            _tool_event("echo.write", {"value": "draft"}, "write-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="write"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert any(isinstance(item.payload, Approval) for item in items)
    assert not any(isinstance(item.payload, Tool) for item in items)
    assert states.get("run-1").status is AgentStatus.INTERRUPTED


async def test_agent_runner_expect_approval_context_overrides_pause_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """runner approval pause는 descriptor의 호출별 approval context를 보존한다."""

    def fake_approval_context(
        self: AgentToolDescriptor, payload: JsonObject
    ) -> AgentToolApprovalContext:
        assert self.schema.name == "echo.write"
        return AgentToolApprovalContext(
            prompt=f"Approve external target: {payload['value']}",
            action_ref=f"external.echo:{payload['value']}",
            metadata={"target": payload["value"]},
        )

    monkeypatch.setattr(AgentToolDescriptor, "approval_context", fake_approval_context)
    model = RecordingModel(
        (
            _tool_event("echo.write", {"value": "draft"}, "write-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="write"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    approval_payloads = [
        item.payload for item in items if isinstance(item.payload, Approval)
    ]
    assert len(approval_payloads) == 1
    approval = approval_payloads[0]

    assert approval.prompt == "Approve external target: draft"
    assert approval.metadata["action_ref"] == "external.echo:draft"
    approval_tool_metadata = cast(JsonObject, approval.metadata["metadata"])
    nested_metadata = cast(JsonObject, approval_tool_metadata["metadata"])
    assert nested_metadata["target"] == "draft"
    assert nested_metadata["arguments_digest"] == _arguments_digest({"value": "draft"})
    assert states.get("run-1").metadata["approval"] == approval.metadata


async def test_agent_runner_expect_model_error_fails_state_and_yields_error() -> None:
    """모델 ERROR 이벤트는 상태를 FAILED로 두고 Error를 노출하며 종료한다."""
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.ERROR,
                error=ModelError(
                    code="rate_limited",
                    message="provider rate limit",
                    retryable=True,
                ),
            ),
        )
    )
    states = FakeStateRepository()

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="boom"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert not any(item.kind is AgentYieldKind.FINAL for item in items)
    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.code == "rate_limited"
    assert states.get("run-1").status is AgentStatus.FAILED


async def test_agent_runner_expect_cancel_signal_pre_loop_terminates() -> None:
    """모델 루프 전 CANCEL signal은 CANCELLED와 cancellation evidence로 끝난다."""
    states = FakeStateRepository()
    evidence = FakeEvidenceRepository()

    signals = FakeSignalRepository(
        (
            AgentSignal(
                id="cancel:run-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.CANCEL,
                payload={"reason": "stop", "requested_by": "tester"},
            ),
        )
    )

    items = await _run_durable(
        RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),)),
        RunAgentInput(state_id="run-1", instruction="cancel"),
        states,
        signals,
        evidence,
    )

    assert len(items) == 1
    assert isinstance(items[0].payload, Cancel)
    assert states.get("run-1").status is AgentStatus.CANCELLED
    assert AgentEvidenceKind.CANCELLATION in {
        artifact.kind for artifact in evidence.list_by_state("run-1")
    }


async def test_agent_runner_expect_cancel_signal_mid_stream_terminates() -> None:
    """스트림 진행 중 도착한 CANCEL signal도 즉시 종료시킨다."""
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    model = _CancelInjectingModel(states, signals)

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="cancel mid"),
        states,
        signals,
        FakeEvidenceRepository(),
    )

    assert any(isinstance(item.payload, Cancel) for item in items)
    assert states.get("run-1").status is AgentStatus.CANCELLED


async def test_agent_runner_expect_user_message_signal_consumed_as_progress() -> None:
    """USER_MESSAGE signal은 progress와 evaluation evidence로 소비된다."""

    states = FakeStateRepository()
    evidence = FakeEvidenceRepository()
    signals = FakeSignalRepository(
        (
            AgentSignal(
                id="user:run-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.USER_MESSAGE,
                payload={"message": "keep it small"},
            ),
        )
    )

    items = await _run_durable(
        RecordingModel(
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.TOKEN_DELTA, token_delta="ok"
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            )
        ),
        RunAgentInput(state_id="run-1", instruction="hello"),
        states,
        signals,
        evidence,
    )

    assert any(
        item.kind is AgentYieldKind.PROGRESS
        and isinstance(item.payload, Progress)
        and item.payload.current_step == "signal"
        for item in items
    )
    assert AgentEvidenceKind.SIGNAL in {
        artifact.kind for artifact in evidence.list_by_state("run-1")
    }

    event_states = FakeStateRepository()
    event_evidence = FakeEvidenceRepository()
    event_signals = FakeSignalRepository(
        (
            AgentSignal(
                id="user:event-run",
                agent_state_id="event-run",
                kind=AgentSignalKind.USER_MESSAGE,
                payload={"message": "keep event parity"},
            ),
        )
    )
    event_model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))
    events = await _run_events_durable(
        event_model,
        RunAgentInput(state_id="event-run", instruction="hello"),
        event_states,
        event_signals,
        event_evidence,
    )
    progress = next(event for event in events if isinstance(event, ArtifactEvent))
    assert progress.content == {
        "kind": AgentYieldKind.PROGRESS.value,
        "message": "user message consumed",
        "current_step": "signal",
        "metadata": {"signal_id": "user:event-run"},
    }
    assert event_signals.list_pending("event-run") == ()


@pytest.mark.parametrize("during_tool", [False, True])
async def test_agent_runner_events_fail_closed_for_unsupported_signal_yield(
    during_tool: bool,
) -> None:
    """A hook shape with no neutral projection becomes one typed terminal event."""
    state_id = f"unsupported-signal-event-{during_tool}"
    states = FakeStateRepository()
    signals = FakeSignalRepository(
        ()
        if during_tool
        else (
            AgentSignal(
                id="steer:unsupported",
                agent_state_id=state_id,
                kind=AgentSignalKind.STEERING_INSTRUCTION,
                payload={"instruction": "token"},
            ),
        )
    )
    evidence = FakeEvidenceRepository()
    model = RecordingModel(
        (
            _tool_event(
                "unsupported.signal_after",
                {"state_id": state_id},
                "signal-1",
            ),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
        if during_tool
        else (ModelStreamEvent(kind=ModelStreamEventKind.DONE),)
    )
    target = UnsupportedSignalProjectionProbeAgent(
        model,
        states,
        signals,
        evidence,
    )

    events = [
        event
        async for event in AgentRunner.for_agent_instance(target).run_events(
            RunAgentInput(state_id=state_id, instruction="steer")
        )
    ]

    terminal = [event for event in events if isinstance(event, RunFinishedEvent)]
    assert len(terminal) == 1
    assert terminal[0].error is not None
    assert terminal[0].error["code"] == "agent_signal_projection_unsupported"
    assert states.get(state_id).status is AgentStatus.FAILED
    assert signals.list_pending(state_id) == ()
    assert AgentEvidenceKind.SIGNAL in {
        item.kind for item in evidence.list_by_state(state_id)
    }
    assert len(model.requests) == 1


async def test_agent_runner_expect_resume_emits_skip_completed_progress() -> None:
    """resume 입력은 persisted boundary로 skip_completed resume 계획을 노출한다."""
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    evidence = FakeEvidenceRepository()

    await _run_durable(
        RecordingModel(
            (
                _tool_event("echo.read", {"value": "x"}, "read-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            )
        ),
        RunAgentInput(state_id="resume-run", instruction="first"),
        states,
        signals,
        evidence,
    )
    items = await _run_durable(
        RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),)),
        RunAgentInput(state_id="resume-run", instruction="again", resume=True),
        states,
        signals,
        evidence,
    )

    assert any(
        item.kind is AgentYieldKind.PROGRESS
        and isinstance(item.payload, Progress)
        and "skip_completed" in item.payload.message
        for item in items
    )


async def test_agent_runner_expect_reasoning_suppressed_when_capability_absent() -> (
    None
):
    """capability가 reasoning을 지원하지 않으면 reasoning delta는 생략된다."""
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.REASONING_DELTA,
                reasoning_delta="thinking",
            ),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="reason"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert not any(isinstance(item.payload, Token) for item in items)


async def test_agent_runner_expect_reasoning_surfaced_when_capability_present() -> None:
    """capability가 reasoning을 지원하면 reasoning delta가 token으로 노출된다."""
    model = _ReasoningModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.REASONING_DELTA,
                reasoning_delta="thinking",
            ),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="reason"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert any(
        isinstance(item.payload, Token) and item.payload.text == "thinking"
        for item in items
    )


async def test_agent_runner_expect_model_selection_passed_to_model_request() -> None:
    """RunAgentInput.model_selection은 ModelRequest.model_selection으로 전달된다."""
    selection = ModelSelection(model_ref="support/primary")
    model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))

    await _collect(
        _invoke_execute(
            StatelessProbeAgent(model),
            RunAgentInput(
                state_id="run-1",
                instruction="reason",
                model_selection=selection,
            ),
        )
    )

    assert model.requests[0].model_selection is selection


async def test_agent_runner_expect_model_selection_used_for_capability() -> None:
    """Runner capability gating consults capability_for() with the run selector."""
    selection = ModelSelection(model_ref="support/primary")
    model = _SelectionAwareReasoningModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.REASONING_DELTA,
                reasoning_delta="thinking",
            ),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )

    items = await _collect(
        _invoke_execute(
            StatelessProbeAgent(model),
            RunAgentInput(
                state_id="run-1",
                instruction="reason",
                model_selection=selection,
            ),
        )
    )

    assert model.capability_selections == [selection]
    assert any(
        isinstance(item.payload, Token) and item.payload.text == "thinking"
        for item in items
    )


async def test_agent_runner_expect_message_delta_surfaced_as_token() -> None:
    """MESSAGE_DELTA는 assistant 텍스트로서 token으로 노출된다."""
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.MESSAGE_DELTA,
                message_delta="hello",
            ),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="say hi"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert any(
        isinstance(item.payload, Token) and item.payload.text == "hello"
        for item in items
    )


async def test_agent_runner_expect_unknown_event_kind_ignored() -> None:
    """surfacing 대상이 아닌 이벤트 종류는 조용히 무시된다."""
    model = RecordingModel(
        (
            ModelStreamEvent(kind=ModelStreamEventKind.PROGRESS),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="progress"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert items[-1].kind is AgentYieldKind.FINAL


async def test_agent_runner_expect_tool_call_without_payload_ignored() -> None:
    """tool_call이 없는 TOOL_CALL_CANDIDATE는 도구 디스패치 없이 무시된다."""
    model = RecordingModel(
        (
            ModelStreamEvent(kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()

    items = await _run_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="empty tool"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert not any(isinstance(item.payload, Tool) for item in items)
    assert items[-1].kind is AgentYieldKind.FINAL


async def test_agent_runner_expect_empty_catalog_sends_no_tool_calling() -> None:
    """도구가 없는 agent의 모델 요청에는 tool_calling이 비어 있다."""
    model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))

    agent = ToollessProbeAgent(model)
    await _collect(
        _invoke_execute(agent, RunAgentInput(state_id="run-1", instruction="x"))
    )

    assert model.requests
    assert model.requests[0].tool_calling is None


async def test_agent_runner_expect_stateless_agent_runs_model_to_final() -> None:
    """durable port가 없는 stateless agent도 model→tool→final로 동작한다."""
    model = RecordingModel(
        (
            _tool_event("echo.read", {"value": "hi"}, "read-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )

    agent = StatelessProbeAgent(model)
    items = await _collect(
        _invoke_execute(agent, RunAgentInput(state_id="run-1", instruction="x"))
    )

    assert any(isinstance(item.payload, Tool) for item in items)
    assert items[-1].kind is AgentYieldKind.FINAL


async def test_agent_runner_expect_stateless_model_error_yields_error_without_final() -> (
    None
):
    """stateless agent의 모델 ERROR도 FINAL 없이 Error를 노출하며 종료한다."""
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.ERROR,
                error=ModelError(code="boom", message="stateless failure"),
            ),
        )
    )

    agent = StatelessProbeAgent(model)
    items = await _collect(
        _invoke_execute(agent, RunAgentInput(state_id="run-1", instruction="x"))
    )

    assert not any(item.kind is AgentYieldKind.FINAL for item in items)
    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.code == "boom"


async def test_agent_runner_expect_missing_model_raises_configuration_error() -> None:
    """IAgentModel 포트가 주입되지 않으면 model configuration error로 실패한다."""

    @Agent(spec=AgentExecutionSpec(name="no_model"))
    class NoModelAgent:
        def __init__(self) -> None:
            self._note = "no model"

    agent = NoModelAgent()
    with pytest.raises(AgentModelConfigurationError):
        AgentRunner.for_agent_instance(agent)


async def test_agent_runner_expect_two_models_injected_raises() -> None:
    """동일 포트가 둘 이상 주입되면 모호하므로 configuration error로 실패한다."""
    model = RecordingModel(())

    @Agent(spec=AgentExecutionSpec(name="two_models"))
    class TwoModelAgent:
        def __init__(self, primary: IAgentModel, secondary: IAgentModel) -> None:
            self._primary = primary
            self._secondary = secondary

    agent = TwoModelAgent(model, RecordingModel(()))
    with pytest.raises(AgentModelConfigurationError):
        AgentRunner.for_agent_instance(agent)


async def test_agent_runner_expect_durable_agent_missing_repository_raises() -> None:
    """durable spec인데 repository 포트가 빠지면 persistence error로 실패한다."""
    model = RecordingModel(())

    @Agent(spec=DURABLE_SPEC, name="durable_partial")
    class DurablePartialAgent:
        def __init__(self, model: IAgentModel) -> None:
            self._model = model

    agent = DurablePartialAgent(model)
    with pytest.raises(AgentPersistenceConfigurationError):
        AgentRunner.for_agent_instance(agent)


async def test_agent_runner_expect_dataclass_tool_result_serialized() -> None:
    """dataclass 도구 결과는 JSON 호환 매핑으로 직렬화된다."""
    result = _serialize_tool_result(EchoRecord(value="rec"))

    assert result == {"value": "rec"}


async def test_agent_runner_expect_basemodel_tool_result_serialized() -> None:
    """pydantic BaseModel 도구 결과는 model_dump로 직렬화된다."""
    result = _serialize_tool_result(EchoResult(value="model"))

    assert result == {"value": "model"}


async def test_agent_runner_expect_sequence_tool_result_serialized() -> None:
    """시퀀스 도구 결과는 JSON 호환 리스트로 직렬화된다."""
    result = _serialize_tool_result([EchoRecord(value="a"), {"k": 1}])

    assert result == [{"value": "a"}, {"k": 1}]


async def test_agent_runner_expect_scalar_tool_result_passthrough() -> None:
    """스칼라 도구 결과는 그대로 통과한다."""
    assert _serialize_tool_result(7) == 7


async def test_agent_runner_expect_unknown_tool_result_type_raises() -> None:
    """직렬화 불가능한 도구 결과는 dispatch error로 거부된다."""
    with pytest.raises(AgentToolDispatchError):
        _serialize_tool_result(object())


async def test_agent_runner_expect_nested_unknown_value_raises() -> None:
    """매핑 내부의 직렬화 불가 값도 dispatch error로 거부된다."""
    with pytest.raises(AgentToolDispatchError):
        _serialize_tool_result({"bad": object()})


@pytest.mark.parametrize(
    ("output_type", "expected_type"),
    [
        (EchoResult, EchoResult),
        (EchoRecord, EchoRecord),
        (EchoTypedDict, dict),
    ],
)
@pytest.mark.parametrize("mode", ["stream", "complete"])
async def test_agent_runner_materializes_declared_structured_output_type(
    output_type: type[object],
    expected_type: type[object],
    mode: str,
) -> None:
    """Stream and complete paths return the exact declared supported output type."""

    exposure = (
        StreamingExposureMode.NO_STREAM_UNTIL_FINAL_GUARDED
        if mode == "complete"
        else StreamingExposureMode.BALANCED
    )

    @Agent(
        spec=AgentExecutionSpec(
            name=f"typed_output_{output_type.__name__}_{mode}",
            output_type=output_type,
            streaming_exposure_mode=exposure,
        )
    )
    class TypedOutputAgent:
        def __init__(self, model: IAgentModel) -> None:
            self._model = model

    payload: JsonObject = {"value": "typed"}
    model: IAgentModel = (
        StructuredCompleteModel((ModelResponse(content="", structured_output=payload),))
        if mode == "complete"
        else StructuredRoundModel(
            (
                (
                    ModelStreamEvent(
                        kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
                        structured_output=payload,
                    ),
                    ModelStreamEvent(kind=ModelStreamEventKind.DONE),
                ),
            )
        )
    )
    agent = TypedOutputAgent(model)
    items = await _collect(
        _invoke_execute(agent, RunAgentInput(state_id="run-1", instruction="x"))
    )

    final = items[-1].payload
    assert isinstance(final, Final)
    assert isinstance(final.output, expected_type)
    assert final.metadata["output_type"] == output_type.__name__
    request = cast(StructuredRoundModel | StructuredCompleteModel, model).requests[0]
    assert request.structured_output is not None
    assert request.structured_output.output_type_name == output_type.__name__
    assert request.structured_output.constraint.schema["additionalProperties"] is False


async def test_agent_runner_events_publish_json_safe_structured_final() -> None:
    """Neutral final metadata carries JSON output and its declared type name."""
    model = StructuredRoundModel(
        (
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
                    structured_output={"value": "typed"},
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    events = [
        event
        async for event in AgentRunner.for_agent_instance(
            StructuredOutputProbeAgent(model)
        ).run_events(RunAgentInput(state_id="structured-event", instruction="answer"))
    ]

    terminal = events[-1]
    assert isinstance(terminal, RunFinishedEvent)
    assert terminal.error is None
    assert terminal.metadata["output"] == {"value": "typed"}
    assert terminal.metadata["output_type"] == "EchoResult"


@pytest.mark.parametrize("surface", ["run", "events"])
@pytest.mark.parametrize(
    ("events", "expected_code"),
    [
        (
            (ModelStreamEvent(kind=ModelStreamEventKind.DONE),),
            "agent_structured_output_missing",
        ),
        (
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.TOKEN_DELTA,
                    token_delta='{"value":"text-only"}',
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            "agent_structured_output_missing",
        ),
        (
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
                    structured_output={"value": "one"},
                ),
                ModelStreamEvent(
                    kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
                    structured_output={"value": "two"},
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            "agent_structured_output_ambiguous",
        ),
        (
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
                    structured_output={"value": 1},
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            "agent_structured_output_invalid",
        ),
    ],
)
async def test_agent_runner_structured_stream_failures_are_typed(
    surface: str,
    events: tuple[ModelStreamEvent, ...],
    expected_code: str,
) -> None:
    """Missing, text fallback, multiple, and invalid stream payloads fail closed."""
    runner = AgentRunner.for_agent_instance(
        StructuredOutputProbeAgent(StructuredRoundModel((events,)))
    )
    command = RunAgentInput(
        state_id=f"structured-{surface}-{expected_code}",
        instruction="answer",
    )
    if surface == "events":
        output_events = [event async for event in runner.run_events(command)]
        terminal = output_events[-1]
        assert isinstance(terminal, RunFinishedEvent)
        assert terminal.error is not None
        assert terminal.error["code"] == expected_code
    else:
        items = await _collect(runner.run(command))
        error = items[-1].payload
        assert isinstance(error, Error)
        assert error.code == expected_code
        assert not any(item.kind is AgentYieldKind.FINAL for item in items)


async def test_agent_runner_complete_invalid_structured_output_is_typed() -> None:
    """Guarded complete materialization uses the same strict invalid code."""
    model = StructuredCompleteModel(
        (ModelResponse(content="", structured_output={"value": 1}),)
    )
    items = await _collect(
        AgentRunner.for_agent_instance(StructuredCompleteProbeAgent(model)).run(
            RunAgentInput(state_id="complete-invalid", instruction="answer")
        )
    )
    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.code == "agent_structured_output_invalid"


@pytest.mark.parametrize("mode", ["stream", "complete"])
async def test_agent_runner_rejects_structured_output_with_tool_calls(
    mode: str,
) -> None:
    """A structured payload cannot authorize or coexist with a tool batch."""
    call = ModelToolCall("echo.read", {"value": "x"}, "call-1")
    model: IAgentModel = (
        StructuredCompleteModel(
            (
                ModelResponse(
                    content="",
                    structured_output={"value": "typed"},
                    tool_calls=(call,),
                ),
            )
        )
        if mode == "complete"
        else StructuredRoundModel(
            (
                (
                    ModelStreamEvent(
                        kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
                        structured_output={"value": "typed"},
                    ),
                    ModelStreamEvent(
                        kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
                        tool_call=call,
                    ),
                    ModelStreamEvent(kind=ModelStreamEventKind.DONE),
                ),
            )
        )
    )
    target = (
        StructuredCompleteToolProbeAgent(model)
        if mode == "complete"
        else StructuredToolProbeAgent(model)
    )
    runner = AgentRunner.for_agent_instance(target)
    items = await _collect(
        runner.run(RunAgentInput(state_id=f"tool-ambiguous-{mode}", instruction="x"))
    )
    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.code == "agent_structured_output_ambiguous"
    assert not any(isinstance(item.payload, Tool) for item in items)


async def test_agent_runner_tool_step_can_precede_structured_final() -> None:
    """Tool-only intermediate steps remain valid before one structured final step."""
    model = StructuredRoundModel(
        (
            (
                _tool_event("echo.read", {"value": "x"}, "call-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
                    structured_output={"value": "typed"},
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    items = await _collect(
        AgentRunner.for_agent_instance(StructuredToolProbeAgent(model)).run(
            RunAgentInput(state_id="structured-after-tool", instruction="answer")
        )
    )
    assert sum(isinstance(item.payload, Tool) for item in items) == 1
    final = items[-1].payload
    assert isinstance(final, Final)
    assert final.output == EchoResult(value="typed")


async def test_agent_runner_preflights_structured_output_capability() -> None:
    """Unsupported selected model fails before stream/complete provider invocation."""
    model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))
    items = await _collect(
        AgentRunner.for_agent_instance(StructuredOutputProbeAgent(model)).run(
            RunAgentInput(state_id="structured-unsupported", instruction="answer")
        )
    )
    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.code == "agent_structured_output_unsupported"
    assert model.requests == []


async def test_agent_runner_expect_default_output_type_metadata_none() -> None:
    """output_type 미선언이면 final metadata의 output_type은 None이다."""
    model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))
    agent = StatelessProbeAgent(model)
    items = await _collect(
        _invoke_execute(agent, RunAgentInput(state_id="run-1", instruction="x"))
    )

    final = items[-1].payload
    assert isinstance(final, Final)
    assert final.metadata["output_type"] is None


def _serialize_tool_result(result: object) -> JsonValue:
    from spakky.agent.runner import _tool_result_json

    return _tool_result_json(result)


class _ReasoningModel(RecordingModel):
    """RecordingModel variant declaring reasoning capability."""

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability(supports_reasoning=True)


class _SelectionAwareReasoningModel(RecordingModel):
    """RecordingModel variant whose capability depends on run model selection."""

    def __init__(self, events: Sequence[ModelStreamEvent]) -> None:
        super().__init__(events)
        self.capability_selections: list[ModelSelection | None] = []

    @override
    def capability_for(
        self,
        selection: ModelSelection | None = None,
    ) -> ModelCapability:
        self.capability_selections.append(selection)
        return ModelCapability(supports_reasoning=selection is not None)


class _CancelInjectingModel(IAgentModel):
    """Model that appends a cancel signal before its first stream event."""

    def __init__(
        self,
        states: FakeStateRepository,
        signals: FakeSignalRepository,
    ) -> None:
        self._states = states
        self._signals = signals

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="unused")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:

        self._signals.append(
            AgentSignal(
                id="cancel:run-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.CANCEL,
                payload={"reason": "mid", "requested_by": "tester"},
            )
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.TOKEN_DELTA, token_delta="t")
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


class _StateMutatingModel(IAgentModel):
    """Model that mutates durable state before yielding DONE."""

    def __init__(
        self,
        states: FakeStateRepository,
        state: AgentState,
    ) -> None:
        self._states = states
        self._state = state

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="unused")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        self._states.save(self._state)
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


class FakeTaskStore(ITaskStore):
    """In-memory conversation-history store keyed by conversation id."""

    def __init__(self) -> None:
        self._histories: dict[str, list[ConversationTurn]] = {}

    @override
    def load_history(self, conversation_id: str) -> tuple[ConversationTurn, ...]:
        return tuple(self._histories.get(conversation_id, ()))

    @override
    def append_turns(
        self,
        conversation_id: str,
        turns: Sequence[ConversationTurn],
    ) -> None:
        self._histories.setdefault(conversation_id, []).extend(turns)


@Agent(spec=AgentExecutionSpec(name="session_probe"))
class SessionProbeAgent:
    """Stateless agent with a session store to exercise multi-turn history."""

    def __init__(self, model: IAgentModel, task_store: ITaskStore) -> None:
        self._model = model
        self._task_store = task_store


@Agent(
    spec=AgentExecutionSpec(
        name="structured_session_probe",
        output_type=EchoResult,
    )
)
class StructuredSessionProbeAgent:
    """Structured-only final target carrying a server-side task store."""

    def __init__(self, model: IAgentModel, task_store: ITaskStore) -> None:
        self._model = model
        self._task_store = task_store


def _user_and_assistant_contents(
    request: ModelRequest,
) -> list[tuple[ModelMessageRole, str]]:
    """Return the non-system messages the runner sent, in order."""
    return [
        (message.role, message.content)
        for message in request.messages
        if message.role is not ModelMessageRole.SYSTEM
    ]


async def test_agent_runner_expect_persisted_session_keeps_multi_turn_history() -> None:
    """같은 conversation의 다음 턴은 영속된 이전 user·assistant 이력을 모델에 싣는다."""
    store = FakeTaskStore()

    first_model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.MESSAGE_DELTA,
                message_delta="a physicist",
            ),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    await _collect(
        _invoke_execute(
            SessionProbeAgent(first_model, store),
            RunAgentInput(
                state_id="turn-1",
                instruction="who was Einstein?",
                conversation_id="thread-7",
            ),
        )
    )

    second_model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))
    await _collect(
        _invoke_execute(
            SessionProbeAgent(second_model, store),
            RunAgentInput(
                state_id="turn-2",
                instruction="his famous equation?",
                conversation_id="thread-7",
            ),
        )
    )

    assert _user_and_assistant_contents(second_model.requests[0]) == [
        (ModelMessageRole.USER, "who was Einstein?"),
        (ModelMessageRole.ASSISTANT, "a physicist"),
        (ModelMessageRole.USER, "his famous equation?"),
    ]
    assert store.load_history("thread-7") == (
        ConversationTurn(ModelMessageRole.USER, "who was Einstein?"),
        ConversationTurn(ModelMessageRole.ASSISTANT, "a physicist"),
        ConversationTurn(ModelMessageRole.USER, "his famous equation?"),
    )


async def test_agent_runner_expect_silent_run_persists_only_user_turn() -> None:
    """assistant 텍스트가 없는 턴은 user turn만 영속해 다음 턴이 질문을 본다."""
    store = FakeTaskStore()

    await _collect(
        _invoke_execute(
            SessionProbeAgent(
                RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),)),
                store,
            ),
            RunAgentInput(
                state_id="turn-1",
                instruction="ping",
                conversation_id="thread-9",
            ),
        )
    )

    assert store.load_history("thread-9") == (
        ConversationTurn(ModelMessageRole.USER, "ping"),
    )


async def test_agent_runner_expect_client_injected_history_seeds_request() -> None:
    """클라이언트가 주입한 이력은 store 없이도 모델 요청을 시드한다."""
    model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))

    await _collect(
        _invoke_execute(
            StatelessProbeAgent(model),
            RunAgentInput(
                state_id="run-1",
                instruction="his famous equation?",
                message_history=(
                    ModelMessage(ModelMessageRole.USER, "who was Einstein?"),
                    ModelMessage(ModelMessageRole.ASSISTANT, "a physicist"),
                ),
            ),
        )
    )

    assert _user_and_assistant_contents(model.requests[0]) == [
        (ModelMessageRole.USER, "who was Einstein?"),
        (ModelMessageRole.ASSISTANT, "a physicist"),
        (ModelMessageRole.USER, "his famous equation?"),
    ]


async def test_agent_runner_expect_client_history_takes_precedence_over_store() -> None:
    """클라이언트 주입 이력이 있으면 영속 store는 조회·기록 모두 건너뛴다."""
    store = FakeTaskStore()
    store.append_turns(
        "thread-7",
        (ConversationTurn(ModelMessageRole.USER, "stored prior turn"),),
    )
    model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))

    await _collect(
        _invoke_execute(
            SessionProbeAgent(model, store),
            RunAgentInput(
                state_id="turn-2",
                instruction="latest",
                conversation_id="thread-7",
                message_history=(
                    ModelMessage(ModelMessageRole.USER, "client prior turn"),
                ),
            ),
        )
    )

    assert _user_and_assistant_contents(model.requests[0]) == [
        (ModelMessageRole.USER, "client prior turn"),
        (ModelMessageRole.USER, "latest"),
    ]
    # The client owns the stateless transcript; the server session stays untouched.
    assert store.load_history("thread-7") == (
        ConversationTurn(ModelMessageRole.USER, "stored prior turn"),
    )


async def test_agent_runner_expect_no_store_run_persists_nothing() -> None:
    """store가 주입되지 않은 stateless 실행은 어떤 turn도 영속하지 않는다."""
    model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))

    items = await _collect(
        _invoke_execute(
            StatelessProbeAgent(model),
            RunAgentInput(state_id="run-1", instruction="x"),
        )
    )

    assert _user_and_assistant_contents(model.requests[0]) == [
        (ModelMessageRole.USER, "x"),
    ]
    assert items[-1].kind is AgentYieldKind.FINAL


async def test_agent_runner_expect_durable_session_persists_history() -> None:
    """durable agent도 task store가 주입되면 멀티턴 이력을 영속한다."""
    store = FakeTaskStore()
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    evidence = FakeEvidenceRepository()

    agent = DurableSessionAgent(
        RecordingModel(
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.MESSAGE_DELTA,
                    message_delta="hi there",
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            )
        ),
        states,
        signals,
        evidence,
        store,
    )
    await _collect(
        _invoke_execute(
            agent,
            RunAgentInput(
                state_id="run-1",
                instruction="hello",
                conversation_id="thread-d",
            ),
        )
    )

    assert store.load_history("thread-d") == (
        ConversationTurn(ModelMessageRole.USER, "hello"),
        ConversationTurn(ModelMessageRole.ASSISTANT, "hi there"),
    )


@Agent(spec=DURABLE_SPEC, name="durable_session")
class DurableSessionAgent:
    """Durable agent carrying a session store alongside its repositories."""

    def __init__(
        self,
        model: IAgentModel,
        states: FakeStateRepository,
        signals: FakeSignalRepository,
        evidence: FakeEvidenceRepository,
        task_store: ITaskStore,
    ) -> None:
        self._model = model
        self._states = states
        self._signals = signals
        self._evidence = evidence
        self._task_store = task_store

    @agent_tool(
        schema_name="echo.write",
        description="Write echo requiring approval.",
        effects=ToolEffects.write_state(),
        idempotency=Idempotency.CONDITIONALLY_IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.REQUIRED,
    )
    def echo_write(self, value: str) -> EchoRecord:
        """Echo a value back after approval."""
        return EchoRecord(value=value)


async def _run_session_events(
    model: IAgentModel,
    store: ITaskStore,
    command: RunAgentInput,
) -> tuple[AgentEvent, ...]:
    runner = AgentRunner.for_agent_instance(SessionProbeAgent(model, store))
    return await _collect_events(runner.run_events(command))


async def test_agent_runner_structured_only_final_persists_one_json_turn() -> None:
    """Structured-only output persists deterministic JSON without duplicate turns."""
    store = FakeTaskStore()
    model = StructuredRoundModel(
        (
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
                    structured_output={"value": "typed"},
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    runner = AgentRunner.for_agent_instance(StructuredSessionProbeAgent(model, store))

    items = await _collect(
        runner.run(
            RunAgentInput(
                state_id="structured-session",
                instruction="answer",
                conversation_id="thread-structured",
            )
        )
    )

    assert sum(item.kind is AgentYieldKind.FINAL for item in items) == 1
    assert store.load_history("thread-structured") == (
        ConversationTurn(ModelMessageRole.USER, "answer"),
        ConversationTurn(ModelMessageRole.ASSISTANT, '{"value":"typed"}'),
    )


async def test_agent_runner_events_expect_session_history_persisted_like_run() -> None:
    """run_events 정상 완료도 run처럼 user·assistant turn을 영속한다."""
    store = FakeTaskStore()
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.MESSAGE_DELTA,
                message_delta="a physicist",
            ),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )

    await _run_session_events(
        model,
        store,
        RunAgentInput(
            state_id="turn-1",
            instruction="who was Einstein?",
            conversation_id="thread-7",
        ),
    )

    assert store.load_history("thread-7") == (
        ConversationTurn(ModelMessageRole.USER, "who was Einstein?"),
        ConversationTurn(ModelMessageRole.ASSISTANT, "a physicist"),
    )


async def test_agent_runner_events_expect_reasoning_not_persisted_as_assistant_turn() -> (
    None
):
    """run_events는 reasoning-only content를 assistant turn으로 영속하지 않는다."""
    store = FakeTaskStore()
    model = _ReasoningModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.REASONING_DELTA,
                reasoning_delta="thinking",
            ),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )

    await _run_session_events(
        model,
        store,
        RunAgentInput(
            state_id="turn-1",
            instruction="reason privately",
            conversation_id="thread-7",
        ),
    )

    assert store.load_history("thread-7") == (
        ConversationTurn(ModelMessageRole.USER, "reason privately"),
    )


async def test_agent_runner_events_expect_error_run_does_not_persist_session() -> None:
    """run_events 모델 ERROR 경로는 대화 turn을 영속하지 않는다."""
    store = FakeTaskStore()
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.ERROR,
                error=ModelError(code="boom", message="provider failed"),
            ),
            ModelStreamEvent(
                kind=ModelStreamEventKind.MESSAGE_DELTA,
                message_delta="must not be exposed",
            ),
        )
    )

    events = await _run_session_events(
        model,
        store,
        RunAgentInput(
            state_id="turn-1",
            instruction="fail",
            conversation_id="thread-7",
        ),
    )

    assert store.load_history("thread-7") == ()
    assert not any(isinstance(event, MessageDeltaEvent) for event in events)


async def test_agent_runner_events_expect_client_history_session_not_persisted() -> (
    None
):
    """client-injected message_history run은 task store에 다시 쓰지 않는다."""
    store = FakeTaskStore()

    await _run_session_events(
        RecordingModel(
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.MESSAGE_DELTA,
                    message_delta="server reply",
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            )
        ),
        store,
        RunAgentInput(
            state_id="turn-1",
            instruction="latest",
            conversation_id="thread-7",
            message_history=(ModelMessage(ModelMessageRole.USER, "client prior turn"),),
        ),
    )

    assert store.load_history("thread-7") == ()


async def test_agent_runner_events_expect_cancelled_session_not_persisted() -> None:
    """run_events CANCEL 경로는 대화 turn을 영속하지 않는다."""

    store = FakeTaskStore()
    signals = FakeSignalRepository(
        (
            AgentSignal(
                id="cancel:run-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.CANCEL,
                payload={"reason": "stop"},
            ),
        )
    )
    runner = AgentRunner.for_agent_instance(
        DurableSessionAgent(
            RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),)),
            FakeStateRepository(),
            signals,
            FakeEvidenceRepository(),
            store,
        )
    )

    await _collect_events(
        runner.run_events(
            RunAgentInput(
                state_id="run-1",
                instruction="cancel",
                conversation_id="thread-7",
            )
        )
    )

    assert store.load_history("thread-7") == ()


async def test_agent_runner_events_expect_paused_session_not_persisted() -> None:
    """run_events approval pause 경로는 대화 turn을 영속하지 않는다."""
    store = FakeTaskStore()
    runner = AgentRunner.for_agent_instance(
        DurableSessionAgent(
            RecordingModel(
                (
                    _tool_event("echo.write", {"value": "draft"}, "write-1"),
                    ModelStreamEvent(kind=ModelStreamEventKind.DONE),
                )
            ),
            FakeStateRepository(),
            FakeSignalRepository(()),
            FakeEvidenceRepository(),
            store,
        )
    )

    await _collect_events(
        runner.run_events(
            RunAgentInput(
                state_id="run-1",
                instruction="write",
                conversation_id="thread-7",
            )
        )
    )

    assert store.load_history("thread-7") == ()


# --- Neutral AgentEvent emission (issue #441 SC-1/SC-2/SC-3) ---


async def _collect_events(
    stream: AsyncIterator[AgentEvent],
) -> tuple[AgentEvent, ...]:
    items: list[AgentEvent] = []
    async for item in stream:
        items.append(item)
    return tuple(items)


async def _run_events_durable(
    model: IAgentModel,
    command: RunAgentInput,
    states: FakeStateRepository,
    signals: FakeSignalRepository,
    evidence: FakeEvidenceRepository,
) -> tuple[AgentEvent, ...]:
    agent = ProbeAgent(model, states, signals, evidence)
    runner = AgentRunner.for_agent_instance(agent)
    return await _collect_events(runner.run_events(command))


def _tool_lifecycle_events(name: str, call_id: str) -> tuple[ModelStreamEvent, ...]:
    """A full C2 model-stream tool-call lifecycle for one call."""
    handle = ModelToolCall(name=name, arguments={}, call_id=call_id)
    return (
        ModelStreamEvent(kind=ModelStreamEventKind.TOOL_CALL_START, tool_call=handle),
        ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_ARGS_DELTA,
            tool_call=handle,
            tool_call_args_delta='{"value":',
        ),
        ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_ARGS_DELTA,
            tool_call=handle,
            tool_call_args_delta='"hi"}',
        ),
        ModelStreamEvent(kind=ModelStreamEventKind.TOOL_CALL_END, tool_call=handle),
        _tool_event(name, {"value": "hi"}, call_id),
    )


async def test_agent_runner_events_expect_tool_call_lifecycle_distinct_events() -> None:
    """SC-1: 도구 1회 호출이 start/args/end/result 구분 AgentEvent로 방출된다."""
    model = RecordingModel(
        (
            *_tool_lifecycle_events("echo.read", "read-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )

    events = await _run_events_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="echo"),
        FakeStateRepository(),
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    start = [event for event in events if isinstance(event, ToolCallStartEvent)]
    args = [event for event in events if isinstance(event, ToolCallArgsDeltaEvent)]
    end = [event for event in events if isinstance(event, ToolCallEndEvent)]
    result = [event for event in events if isinstance(event, ToolCallResultEvent)]
    assert [event.kind for event in (start[0], args[0], end[0], result[0])] == [
        AgentEventKind.TOOL_CALL_START,
        AgentEventKind.TOOL_CALL_ARGS_DELTA,
        AgentEventKind.TOOL_CALL_END,
        AgentEventKind.TOOL_CALL_RESULT,
    ]
    assert start[0].tool_name == "echo.read"
    assert "".join(event.args_delta for event in args) == '{"value":"hi"}'
    assert result[0].result == {"value": "hi"}
    assert {event.call_id for event in (start[0], args[0], end[0], result[0])} == {
        "read-1"
    }


async def test_agent_runner_events_expect_local_teammate_events_join_parent_stream() -> (
    None
):
    """teammate tool 호출이 child neutral events를 parent stream에 합류시킨다."""
    child = ResearcherAgent(
        RecordingModel(
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.MESSAGE_DELTA,
                    message_delta="child-result",
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            )
        )
    )
    parent = OrchestratorAgent(
        RecordingModel(
            (
                _tool_event(
                    "teammate.researcher.delegate",
                    {"instruction": "inspect the repo"},
                    "delegate-1",
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            )
        ),
        child,
    )
    runner = AgentRunner.for_agent_instance(parent)

    events = await _collect_events(
        runner.run_events(RunAgentInput(state_id="parent-run", instruction="delegate"))
    )

    child_messages = [
        event
        for event in events
        if isinstance(event, MessageDeltaEvent)
        and event.attribution.agent_id == "researcher"
    ]
    parent_results = [
        event for event in events if isinstance(event, ToolCallResultEvent)
    ]
    assert child_messages[0].delta == "child-result"
    assert child_messages[0].attribution.parent_run_id == "parent-run"
    assert child_messages[0].attribution.conversation_id == "parent-run"
    assert parent_results[0].tool_name == "teammate.researcher.delegate"
    result_payload = parent_results[0].result
    assert isinstance(result_payload, Mapping)
    assert result_payload["summary"] == "teammate 'researcher' completed"


async def test_agent_runner_events_expect_message_and_reasoning_distinguished() -> None:
    """SC-2: message와 reasoning이 구분된 AgentEvent로 방출된다."""
    model = _ReasoningModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.MESSAGE_DELTA,
                message_delta="answer",
            ),
            ModelStreamEvent(
                kind=ModelStreamEventKind.REASONING_DELTA,
                reasoning_delta="thinking",
            ),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )

    events = await _run_events_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="say hi"),
        FakeStateRepository(),
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    messages = [event for event in events if isinstance(event, MessageDeltaEvent)]
    reasoning = [event for event in events if isinstance(event, ReasoningDeltaEvent)]
    assert [event.delta for event in messages] == ["answer"]
    assert [event.delta for event in reasoning] == ["thinking"]
    assert messages[0].message_id != reasoning[0].reasoning_id


async def test_agent_runner_events_expect_token_delta_projected_as_message() -> None:
    """generic TOKEN_DELTA 채널도 message delta AgentEvent로 투영된다."""
    model = RecordingModel(
        (
            ModelStreamEvent(kind=ModelStreamEventKind.TOKEN_DELTA, token_delta="tok"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )

    events = await _run_events_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="x"),
        FakeStateRepository(),
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    messages = [event for event in events if isinstance(event, MessageDeltaEvent)]
    assert [event.delta for event in messages] == ["tok"]


async def test_agent_runner_events_expect_adapters_build_lossless_frames() -> None:
    """SC-3: 어댑터가 러너 이벤트 출력에서 무손실 프레임을 구성할 수 있다."""
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.MESSAGE_DELTA, message_delta="hi"
            ),
            *_tool_lifecycle_events("echo.read", "read-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )

    events = await _run_events_durable(
        model,
        RunAgentInput(
            state_id="run-1",
            instruction="echo",
            conversation_id="thread-1",
        ),
        FakeStateRepository(),
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    for event in events:
        ag_ui = _to_ag_ui(event)
        a2a = _to_a2a(event)
        assert ag_ui["threadId"] == a2a["contextId"] == "thread-1"
        assert ag_ui["runId"] == a2a["taskId"] == "run-1"
        assert ag_ui["type"]
    result = next(event for event in events if isinstance(event, ToolCallResultEvent))
    assert _to_ag_ui(result)["messageId"] == result.message_id


async def test_agent_runner_events_expect_run_and_step_lifecycle_wraps_loop() -> None:
    """run/step lifecycle 이벤트가 모델 루프를 감싸 RUN/STEP 합성을 가능케 한다."""
    events = await _run_events_durable(
        RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),)),
        RunAgentInput(state_id="run-1", instruction="x"),
        FakeStateRepository(),
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert isinstance(events[0], RunStartedEvent)
    assert isinstance(events[1], StepStartedEvent)
    assert isinstance(events[-2], StepFinishedEvent)
    assert isinstance(events[-1], RunFinishedEvent)
    assert events[-1].error is None


async def test_agent_runner_events_expect_completed_durable_state_after_run() -> None:
    """durable 실행은 이벤트 스트림 종료 시 상태를 COMPLETED로 전이한다."""
    states = FakeStateRepository()

    await _run_events_durable(
        RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),)),
        RunAgentInput(state_id="run-1", instruction="x"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert states.get("run-1").status is AgentStatus.COMPLETED


async def test_agent_runner_events_expect_model_error_emits_run_error() -> None:
    """모델 ERROR 이벤트는 RunFinished의 error로 노출되며 종료한다."""
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.ERROR,
                error=ModelError(code="boom", message="provider failed"),
            ),
        )
    )

    events = await _run_events_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="x"),
        FakeStateRepository(),
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    finished = events[-1]
    assert isinstance(finished, RunFinishedEvent)
    assert finished.error == {
        "code": "boom",
        "message": "provider failed",
        "retryable": False,
        "metadata": {
            "model_steps": 1,
            "tool_calls": 0,
            "total_tokens": 0,
            "usage": {},
        },
    }


async def test_agent_runner_events_expect_cancel_signal_pre_loop_terminates() -> None:
    """run_events 경로도 모델 호출 전 CANCEL signal을 terminal error로 방출한다."""

    states = FakeStateRepository()
    signals = FakeSignalRepository(
        (
            AgentSignal(
                id="cancel:run-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.CANCEL,
                payload={"reason": "stop"},
            ),
        )
    )

    events = await _run_events_durable(
        RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),)),
        RunAgentInput(state_id="run-1", instruction="cancel"),
        states,
        signals,
        FakeEvidenceRepository(),
    )

    assert len(events) == 2
    assert isinstance(events[0], RunStartedEvent)
    finished = events[1]
    assert isinstance(finished, RunFinishedEvent)
    assert finished.error is not None
    assert finished.error == {
        "code": "cancelled",
        "message": "stop",
        "metadata": {
            "state": AgentStatus.CANCELLED.value,
            "signal_id": "cancel:run-1",
        },
    }
    assert states.get("run-1").status is AgentStatus.CANCELLED


async def test_agent_runner_events_expect_reasoning_suppressed_without_capability() -> (
    None
):
    """capability가 reasoning을 지원하지 않으면 reasoning AgentEvent는 생략된다."""
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.REASONING_DELTA,
                reasoning_delta="thinking",
            ),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )

    events = await _run_events_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="x"),
        FakeStateRepository(),
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert not any(isinstance(event, ReasoningDeltaEvent) for event in events)


async def test_agent_runner_events_expect_approval_gate_blocks_result_emission() -> (
    None
):
    """승인 미결 도구는 RunFinished(success) 대신 pause event로 멈춘다."""
    model = RecordingModel(
        (
            _tool_event("echo.write", {"value": "draft"}, "write-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = FakeStateRepository()

    events = await _run_events_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="write"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert not any(isinstance(event, ToolCallResultEvent) for event in events)
    assert not any(
        isinstance(event, RunFinishedEvent) and event.error is None for event in events
    )
    pause = events[-1]
    assert isinstance(pause, RunPausedEvent)
    assert pause.reason is AgentStateReason.APPROVAL_REQUIRED
    assert pause.prompt == "Approve tool invocation: echo_write"
    assert pause.approval_id == _approval_request_id(
        "run-1", "write-1", {"value": "draft"}
    )
    assert pause.tool_call_id == "write-1"
    assert pause.allowed_decisions == ("approve", "reject", "modify", "defer", "cancel")
    paused = states.get("run-1")
    assert paused.status is AgentStatus.INTERRUPTED
    assert paused.reason is AgentStateReason.APPROVAL_REQUIRED


async def test_agent_runner_events_expect_approved_tool_emits_result() -> None:
    """승인 결정 수신 도구는 dispatch 후 tool result AgentEvent를 방출한다."""
    model = RecordingModel(
        (
            _tool_event("echo.write", {"value": "draft"}, "write-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    signals = FakeSignalRepository(
        (
            _approval_signal(
                "run-1",
                _approval_request_id("run-1", "write-1", {"value": "draft"}),
                "approve",
            ),
        )
    )

    events = await _run_events_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="write"),
        FakeStateRepository(),
        signals,
        FakeEvidenceRepository(),
    )

    result = [event for event in events if isinstance(event, ToolCallResultEvent)]
    assert result[0].tool_name == "echo.write"


async def test_agent_runner_events_expect_rejected_approval_emits_error_finish() -> (
    None
):
    """승인 거부는 pause가 아니라 failed RunFinishedEvent로 종단된다."""
    model = RecordingModel(
        (
            _tool_event("echo.write", {"value": "draft"}, "write-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    signals = FakeSignalRepository(
        (
            _approval_signal(
                "run-1",
                _approval_request_id("run-1", "write-1", {"value": "draft"}),
                "reject",
            ),
        )
    )

    events = await _run_events_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="write"),
        FakeStateRepository(),
        signals,
        FakeEvidenceRepository(),
    )

    finished = events[-1]
    assert isinstance(finished, RunFinishedEvent)
    assert finished.error is not None
    assert finished.error["code"] == "approval_rejected"
    assert not any(isinstance(event, RunPausedEvent) for event in events)


async def test_agent_runner_events_expect_unknown_stream_event_ignored() -> None:
    """surfacing 대상이 아닌 모델 이벤트 종류는 조용히 무시된다."""
    events = await _run_events_durable(
        RecordingModel(
            (
                ModelStreamEvent(kind=ModelStreamEventKind.PROGRESS),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            )
        ),
        RunAgentInput(state_id="run-1", instruction="x"),
        FakeStateRepository(),
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert isinstance(events[-1], RunFinishedEvent)
    assert not any(isinstance(event, MessageDeltaEvent) for event in events)


async def test_agent_runner_events_expect_auth_interrupt_after_stream_pauses() -> None:
    """model stream 종료 시점의 auth_required state도 RunPausedEvent로 노출된다."""
    states = FakeStateRepository()
    model = _StateMutatingModel(
        states,
        AgentState(
            id="run-1",
            agent_type="runner_probe",
            status=AgentStatus.INTERRUPTED,
            transition=AgentStateTransition.INTERRUPTED,
            reason=AgentStateReason.AUTH_REQUIRED,
            current_activity="Sign in to continue.",
        ),
    )

    events = await _run_events_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="needs auth"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    pause = events[-1]
    assert isinstance(pause, RunPausedEvent)
    assert pause.reason is AgentStateReason.AUTH_REQUIRED
    assert pause.prompt == "Sign in to continue."
    assert pause.approval_id is None
    assert pause.allowed_decisions == ()


async def test_agent_runner_events_expect_failed_state_after_stream_emits_error() -> (
    None
):
    """model stream 종료 시점의 failed state는 상태 reason 기반 error로 종단된다."""
    states = FakeStateRepository()
    model = _StateMutatingModel(
        states,
        AgentState(
            id="run-1",
            agent_type="runner_probe",
            status=AgentStatus.FAILED,
            transition=AgentStateTransition.FAILED,
            reason=None,
        ),
    )

    events = await _run_events_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="fail late"),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    finished = events[-1]
    assert isinstance(finished, RunFinishedEvent)
    assert finished.error is not None
    assert finished.error["code"] == "failed"


def test_run_paused_event_helper_expect_accepts_top_level_tool_call_id() -> None:
    """approval metadata의 top-level call_id도 pause event 필드로 승격된다."""
    from spakky.agent.runner import _run_paused_event

    event = _run_paused_event(
        AgentState(
            id="run-1",
            agent_type="runner_probe",
            status=AgentStatus.INTERRUPTED,
            reason=AgentStateReason.APPROVAL_REQUIRED,
            current_activity="Approve?",
            metadata={
                "approval": {
                    "id": "approval-1",
                    "call_id": "call-1",
                    "allowed_decisions": ["approve"],
                    "metadata": "legacy",
                }
            },
        ),
        AgentEventAttribution(
            agent_id="runner_probe",
            run_id="run-1",
            conversation_id="run-1",
        ),
    )

    assert event.tool_call_id == "call-1"
    assert event.allowed_decisions == ("approve",)


def test_run_paused_event_helper_expect_ignores_non_list_allowed_decisions() -> None:
    """단일 문자열 allowed_decisions는 문자 단위로 분해되지 않고 빈 목록이 된다."""
    from spakky.agent.runner import _run_paused_event

    event = _run_paused_event(
        AgentState(
            id="run-1",
            agent_type="runner_probe",
            status=AgentStatus.INTERRUPTED,
            reason=AgentStateReason.APPROVAL_REQUIRED,
            current_activity="Approve?",
            metadata={
                "approval": {
                    "id": "approval-1",
                    "call_id": "call-1",
                    "allowed_decisions": "approve",
                }
            },
        ),
        AgentEventAttribution(
            agent_id="runner_probe",
            run_id="run-1",
            conversation_id="run-1",
        ),
    )

    assert event.allowed_decisions == ()


def test_cancel_error_helper_expect_fallback_for_non_cancel_payload() -> None:
    """cancel error helper는 예상 밖 payload에서도 generic cancelled error를 낸다."""
    from spakky.agent.runner import _cancel_error

    error = _cancel_error(
        AgentYield(kind=AgentYieldKind.PROGRESS, payload=Progress("x"))
    )

    assert error == {"code": "cancelled", "message": "run cancelled"}


async def test_agent_runner_events_expect_cancel_signal_mid_stream_terminates() -> None:
    """run_events 경로도 모델 스트림 중 도착한 CANCEL signal을 소비한다."""
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    model = _CancelInjectingModel(states, signals)

    events = await _run_events_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="cancel mid"),
        states,
        signals,
        FakeEvidenceRepository(),
    )

    assert states.get("run-1").status is AgentStatus.CANCELLED
    finished = events[-1]
    assert isinstance(finished, RunFinishedEvent)
    assert finished.error is not None
    assert finished.error == {
        "code": "cancelled",
        "message": "mid",
        "metadata": {
            "state": AgentStatus.CANCELLED.value,
            "signal_id": "cancel:run-1",
            "requested_by": "tester",
        },
    }
    assert sum(isinstance(event, RunFinishedEvent) for event in events) == 1
    assert not any(isinstance(event, RunPausedEvent) for event in events)


async def test_agent_runner_events_expect_stateless_agent_emits_events() -> None:
    """durable port가 없는 stateless agent도 이벤트 스트림을 방출한다."""
    model = RecordingModel(
        (
            _tool_event("echo.read", {"value": "hi"}, "read-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    agent = StatelessProbeAgent(model)
    runner = AgentRunner.for_agent_instance(agent)

    events = await _collect_events(
        runner.run_events(RunAgentInput(state_id="run-1", instruction="x"))
    )

    assert isinstance(events[0], RunStartedEvent)
    assert any(isinstance(event, ToolCallResultEvent) for event in events)
    assert isinstance(events[-1], RunFinishedEvent)


async def test_agent_runner_events_expect_missing_call_id_uses_step_index() -> None:
    """call_id가 없는 호출은 model step과 batch index로 unique하게 연결된다."""
    handle = ModelToolCall(name="echo.read", arguments={"value": "hi"}, call_id=None)
    model = RecordingModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.TOOL_CALL_START, tool_call=handle
            ),
            ModelStreamEvent(
                kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE, tool_call=handle
            ),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )

    events = await _run_events_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="x"),
        FakeStateRepository(),
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    start = next(event for event in events if isinstance(event, ToolCallStartEvent))
    result = next(event for event in events if isinstance(event, ToolCallResultEvent))
    assert start.call_id == result.call_id == "run-1:model-1:call-1"


async def test_agent_runner_events_expect_fine_grained_tool_events_without_payload() -> (
    None
):
    """tool_call이 없는 미세 도구 채널 이벤트는 boundary AgentEvent를 방출하지 않는다."""
    model = RecordingModel(
        (
            ModelStreamEvent(kind=ModelStreamEventKind.TOOL_CALL_START),
            ModelStreamEvent(kind=ModelStreamEventKind.TOOL_CALL_ARGS_DELTA),
            ModelStreamEvent(kind=ModelStreamEventKind.TOOL_CALL_END),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )

    events = await _run_events_durable(
        model,
        RunAgentInput(state_id="run-1", instruction="x"),
        FakeStateRepository(),
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert not any(isinstance(event, ToolCallStartEvent) for event in events)
    assert not any(isinstance(event, ToolCallEndEvent) for event in events)


# A 1-message sliding window plus a low threshold makes the trip deterministic:
# the injected history below estimates well past the threshold, so compaction
# always runs and keeps exactly the final message.
@Agent(
    spec=AgentExecutionSpec(
        name="compacting_probe",
        compaction=AgentCompactionPolicy(
            strategies=(KeepRecentMessagesCompactionStrategy(max_messages=1),),
            trigger_token_threshold=4,
        ),
    )
)
class CompactingProbeAgent:
    """Stateless agent that declares a sliding-window compaction policy."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model


def _long_history() -> tuple[ModelMessage, ...]:
    """History whose estimated tokens exceed the probe's threshold of 4."""
    return (
        ModelMessage(ModelMessageRole.USER, "x" * 40),
        ModelMessage(ModelMessageRole.ASSISTANT, "y" * 40),
        ModelMessage(ModelMessageRole.USER, "z" * 40),
    )


async def test_agent_runner_expect_compaction_applies_when_threshold_tripped() -> None:
    """선언된 compaction은 임계치를 넘은 이력을 모델 요청 전에 자동 압축한다."""
    model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))

    await _collect(
        _invoke_execute(
            CompactingProbeAgent(model),
            RunAgentInput(
                state_id="run-1",
                instruction="latest",
                message_history=_long_history(),
            ),
        )
    )

    assert _user_and_assistant_contents(model.requests[0]) == [
        (ModelMessageRole.USER, "z" * 40),
        (ModelMessageRole.USER, "latest"),
    ]


async def test_agent_runner_expect_compaction_skipped_below_threshold() -> None:
    """추정 토큰이 임계치 미만이면 compaction은 이력을 그대로 통과시킨다."""
    model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))

    await _collect(
        _invoke_execute(
            CompactingProbeAgent(model),
            RunAgentInput(
                state_id="run-1",
                instruction="latest",
                message_history=(
                    ModelMessage(ModelMessageRole.USER, "hi"),
                    ModelMessage(ModelMessageRole.ASSISTANT, "yo"),
                ),
            ),
        )
    )

    assert _user_and_assistant_contents(model.requests[0]) == [
        (ModelMessageRole.USER, "hi"),
        (ModelMessageRole.ASSISTANT, "yo"),
        (ModelMessageRole.USER, "latest"),
    ]


@Agent(
    spec=AgentExecutionSpec(
        name="chained_compacting_probe",
        compaction=AgentCompactionPolicy(
            strategies=(
                TrimToolResultsCompactionStrategy(max_characters=4),
                KeepRecentMessagesCompactionStrategy(max_messages=2),
            ),
            trigger_token_threshold=4,
        ),
    )
)
class ChainedCompactingProbeAgent:
    """Agent that chains tool-result trimming ahead of a sliding window."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model


async def test_agent_runner_expect_compaction_chain_applies_in_declared_order() -> None:
    """compaction 체인은 선언 순서대로 적용된다(트리밍 후 슬라이딩 윈도우)."""
    model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))

    await _collect(
        _invoke_execute(
            ChainedCompactingProbeAgent(model),
            RunAgentInput(
                state_id="run-1",
                instruction="latest",
                message_history=(
                    ModelMessage(ModelMessageRole.USER, "u" * 40),
                    ModelMessage(
                        ModelMessageRole.ASSISTANT,
                        "calling",
                        metadata={
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "name": "echo.read",
                                    "arguments": {"value": "x"},
                                }
                            ]
                        },
                    ),
                    ModelMessage(
                        ModelMessageRole.TOOL,
                        "0123456789",
                        metadata={
                            "call_id": "call-1",
                            "tool_name": "echo.read",
                        },
                    ),
                    ModelMessage(ModelMessageRole.ASSISTANT, "a" * 40),
                ),
            ),
        )
    )

    assert _user_and_assistant_contents(model.requests[0]) == [
        (ModelMessageRole.ASSISTANT, "calling"),
        (ModelMessageRole.TOOL, "0123"),
        (ModelMessageRole.ASSISTANT, "a" * 40),
        (ModelMessageRole.USER, "latest"),
    ]


@Agent(
    spec=AgentExecutionSpec(
        name="event_compacting_probe",
        compaction=AgentCompactionPolicy(
            strategies=(KeepRecentMessagesCompactionStrategy(max_messages=1),),
            trigger_token_threshold=4,
        ),
    )
)
class EventCompactingProbeAgent:
    """Compacting agent exercised through the neutral event stream."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model


class OrphaningCompactionStrategy(ICompactionStrategy):
    """Invalid custom strategy that drops the assistant side of a tool group."""

    @override
    async def compact(
        self,
        history: tuple[ModelMessage, ...],
        usage: ModelUsage,
        capability: ModelCapability,
    ) -> tuple[ModelMessage, ...]:
        return (history[-1],)


@Agent(
    spec=AgentExecutionSpec(
        name="orphaning_compaction_probe",
        compaction=AgentCompactionPolicy(
            strategies=(OrphaningCompactionStrategy(),),
            trigger_token_threshold=1,
        ),
    )
)
class OrphaningCompactionProbeAgent:
    """Runner target proving custom compaction output is validated per stage."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model


async def test_agent_runner_expect_event_stream_also_compacts_history() -> None:
    """neutral event 스트림(run_events) 경로도 동일하게 이력을 압축한다."""
    model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))
    runner = AgentRunner.for_agent_instance(EventCompactingProbeAgent(model))

    events: list[AgentEvent] = []
    async for event in runner.run_events(
        RunAgentInput(
            state_id="run-1",
            instruction="latest",
            message_history=_long_history(),
        )
    ):
        events.append(event)

    assert any(isinstance(event, RunFinishedEvent) for event in events)
    assert _user_and_assistant_contents(model.requests[0]) == [
        (ModelMessageRole.USER, "z" * 40),
        (ModelMessageRole.USER, "latest"),
    ]


@pytest.mark.parametrize("surface", ["run", "events"])
async def test_agent_runner_rejects_custom_compaction_orphan_before_provider(
    surface: str,
) -> None:
    """Every custom strategy result is validated before a provider request."""
    model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))
    runner = AgentRunner.for_agent_instance(OrphaningCompactionProbeAgent(model))
    history = (
        ModelMessage(
            ModelMessageRole.ASSISTANT,
            "calling",
            metadata={
                "tool_calls": [{"id": "call-1", "name": "echo.read", "arguments": {}}]
            },
        ),
        ModelMessage(
            ModelMessageRole.TOOL,
            "result",
            metadata={"call_id": "call-1", "tool_name": "echo.read"},
        ),
    )
    command = RunAgentInput(
        state_id=f"orphan-{surface}",
        instruction="latest",
        message_history=history,
    )

    if surface == "events":
        events = [event async for event in runner.run_events(command)]
        terminal = events[-1]
        assert isinstance(terminal, RunFinishedEvent)
        assert terminal.error is not None
        assert terminal.error["code"] == "agent_model_execution_failed"
    else:
        items = await _collect(runner.run(command))
        error = items[-1].payload
        assert isinstance(error, Error)
        assert error.code == "agent_model_execution_failed"
    assert model.requests == []


async def test_agent_runner_expect_summarize_strategy_uses_injected_model() -> None:
    """요약 전략은 주입된 모델로 오래된 턴을 요약해 모델 요청을 압축한다."""
    summarizer = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))
    strategy = SummarizeOldTurnsCompactionStrategy(model=summarizer, keep_recent=1)

    @Agent(
        spec=AgentExecutionSpec(
            name="summarizing_runner_probe",
            compaction=AgentCompactionPolicy(
                strategies=(strategy,),
                trigger_token_threshold=4,
            ),
        )
    )
    class SummarizingRunnerProbeAgent:
        def __init__(self, model: IAgentModel) -> None:
            self._model = model

    main_model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))
    await _collect(
        _invoke_execute(
            SummarizingRunnerProbeAgent(main_model),
            RunAgentInput(
                state_id="run-1",
                instruction="latest",
                message_history=_long_history(),
            ),
        )
    )

    seeded = _user_and_assistant_contents(main_model.requests[0])
    assert seeded[0] == (ModelMessageRole.EVIDENCE, "recorded")
    assert seeded[-2] == (ModelMessageRole.USER, "z" * 40)
    assert seeded[-1] == (ModelMessageRole.USER, "latest")


async def test_iterative_runner_tool_once_then_final_continues_model_history() -> None:
    """한 tool round 뒤 TOOL history를 포함해 다음 model step에서 final을 만든다."""
    model = ScriptedRoundModel(
        (
            (
                _tool_event("echo.read", {"value": "one"}, "call-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.TOKEN_DELTA,
                    token_delta="finished",
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )

    items = await _collect(
        _invoke_execute(
            StatelessProbeAgent(model),
            RunAgentInput(state_id="iter-1", instruction="echo"),
        )
    )

    assert len(model.requests) == 2
    assert sum(item.kind is AgentYieldKind.TOOL for item in items) == 1
    assert sum(item.kind is AgentYieldKind.FINAL for item in items) == 1
    continued = model.requests[1].messages
    assistant = next(
        message for message in continued if message.role is ModelMessageRole.ASSISTANT
    )
    tool = next(
        message for message in continued if message.role is ModelMessageRole.TOOL
    )
    assert assistant.metadata["tool_calls"] == [
        {
            "id": "call-1",
            "name": "echo.read",
            "arguments": {"value": "one"},
        }
    ]
    assert tool.metadata == {"call_id": "call-1", "tool_name": "echo.read"}


async def test_iterative_runner_preserves_multiple_round_and_batch_order() -> None:
    """여러 model round와 한 response의 복수 calls가 선언 순서대로 이어진다."""
    model = ScriptedRoundModel(
        (
            (
                _tool_event("echo.read", {"value": "a"}, "a-1"),
                _tool_event("echo.read", {"value": "b"}, "b-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (
                _tool_event("echo.read", {"value": "c"}, "c-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.MESSAGE_DELTA,
                    message_delta="done",
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )

    items = await _collect(
        _invoke_execute(
            StatelessProbeAgent(model),
            RunAgentInput(state_id="iter-2", instruction="echo three"),
        )
    )

    tools = [item.payload for item in items if isinstance(item.payload, Tool)]
    assert [tool.arguments["value"] for tool in tools] == ["a", "b", "c"]
    assert len(model.requests) == 3
    assert [
        message.metadata["call_id"]
        for message in model.requests[2].messages
        if message.role is ModelMessageRole.TOOL
    ] == ["a-1", "b-1", "c-1"]


async def test_iterative_runner_invalid_batch_dispatches_nothing() -> None:
    """Batch 하나가 unregistered이면 valid prefix도 실제 실행하지 않는다."""
    model = ScriptedRoundModel(
        (
            (
                _tool_event("batch.record", {"value": "must-not-run"}, "valid-1"),
                _tool_event("missing.tool", {}, "invalid-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    agent = BatchProbeAgent(model)

    items = await _collect(
        _invoke_execute(
            agent,
            RunAgentInput(state_id="batch-invalid", instruction="record"),
        )
    )

    assert agent.dispatched == []
    assert not any(item.kind is AgentYieldKind.TOOL for item in items)
    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.code == "agent_tool_batch_invalid"


async def test_iterative_runner_missing_ids_are_unique_within_same_name_batch() -> None:
    """동일-name calls도 step/index correlation으로 history와 results가 분리된다."""
    model = ScriptedRoundModel(
        (
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
                    tool_call=ModelToolCall("echo.read", {"value": "a"}),
                ),
                ModelStreamEvent(
                    kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
                    tool_call=ModelToolCall("echo.read", {"value": "b"}),
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (ModelStreamEvent(kind=ModelStreamEventKind.DONE),),
        )
    )

    items = await _collect(
        _invoke_execute(
            StatelessProbeAgent(model),
            RunAgentInput(state_id="missing-ids", instruction="echo"),
        )
    )

    calls = [item.payload for item in items if isinstance(item.payload, Tool)]
    assert [call.call_id for call in calls] == [
        "missing-ids:model-1:call-1",
        "missing-ids:model-1:call-2",
    ]


async def test_iterative_runner_approval_pause_resume_continues_without_model_replay() -> (
    None
):
    """Fresh runner는 pending batch를 복원·승인·dispatch한 뒤 다음 model로 간다."""
    model = ScriptedRoundModel(
        (
            (
                _tool_event("echo.write", {"value": "draft"}, "write-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.TOKEN_DELTA,
                    token_delta="published",
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    evidence = FakeEvidenceRepository()

    paused = await _run_durable(
        model,
        RunAgentInput(state_id="resume-1", instruction="write"),
        states,
        signals,
        evidence,
    )
    approval = next(
        item.payload for item in paused if isinstance(item.payload, Approval)
    )
    assert states.get("resume-1").input_ref == "write"
    assert len(model.requests) == 1
    signals.append(_approval_signal("resume-1", approval.id, "approve"))

    resumed = await _run_durable(
        model,
        RunAgentInput(state_id="resume-1", instruction="write", resume=True),
        states,
        signals,
        evidence,
    )

    assert any(isinstance(item.payload, Tool) for item in resumed)
    assert resumed[-1].kind is AgentYieldKind.FINAL
    assert len(model.requests) == 2
    assert any(
        message.role is ModelMessageRole.TOOL for message in model.requests[1].messages
    )


async def test_iterative_runner_modify_dispatches_only_approved_arguments() -> None:
    """MODIFY decision은 original args가 아니라 검증된 modified payload를 실행한다."""
    model = ScriptedRoundModel(
        (
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
                    tool_call=ModelToolCall(
                        "echo.write",
                        {"value": "raw"},
                        "write-1",
                        metadata={"thought_signature": "provider-signature"},
                    ),
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (ModelStreamEvent(kind=ModelStreamEventKind.DONE),),
        )
    )
    request_id = _approval_request_id("modify-1", "write-1", {"value": "raw"})
    signal = _approval_signal("modify-1", request_id, "modify")
    signal = replace(
        signal,
        payload={
            **signal.payload,
            "modified_payload": {"value": "approved"},
        },
    )

    items = await _run_durable(
        model,
        RunAgentInput(state_id="modify-1", instruction="write"),
        FakeStateRepository(),
        FakeSignalRepository((signal,)),
        FakeEvidenceRepository(),
    )

    tool = next(item.payload for item in items if isinstance(item.payload, Tool))
    assert tool.arguments == {"value": "approved"}
    assert tool.result == {"value": "approved"}
    assistant = next(
        message
        for message in model.requests[1].messages
        if message.role is ModelMessageRole.ASSISTANT
    )
    assert assistant.metadata["tool_calls"] == [
        {
            "thought_signature": "provider-signature",
            "id": "write-1",
            "name": "echo.write",
            "arguments": {"value": "approved"},
        }
    ]


@pytest.mark.parametrize("surface", ["run", "events"])
async def test_iterative_invalid_modified_approval_is_typed_and_dispatches_nothing(
    surface: str,
) -> None:
    """A MODIFY payload that cannot bind fails as agent_approval_invalid."""
    state_id = f"invalid-modify-{surface}"
    request_id = _approval_request_id(state_id, "write-1", {"value": "raw"})
    signal = replace(
        _approval_signal(state_id, request_id, "modify"),
        payload={
            "request_id": request_id,
            "decision": "modify",
            "modified_payload": {"unknown": "value"},
        },
    )
    states = FakeStateRepository()
    evidence = FakeEvidenceRepository()
    model = ScriptedRoundModel(
        (
            (
                _tool_event("echo.write", {"value": "raw"}, "write-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    target = ProbeAgent(model, states, FakeSignalRepository((signal,)), evidence)
    runner = AgentRunner.for_agent_instance(target)
    command = RunAgentInput(state_id=state_id, instruction="modify")

    if surface == "events":
        events = [event async for event in runner.run_events(command)]
        terminal = events[-1]
        assert isinstance(terminal, RunFinishedEvent)
        assert terminal.error is not None
        assert terminal.error["code"] == "agent_approval_invalid"
        assert not any(isinstance(event, ToolCallResultEvent) for event in events)
    else:
        items = await _collect(runner.run(command))
        error = items[-1].payload
        assert isinstance(error, Error)
        assert error.code == "agent_approval_invalid"
        assert not any(isinstance(item.payload, Tool) for item in items)
    assert states.get(state_id).status is AgentStatus.FAILED
    assert AgentEvidenceKind.TOOL not in {
        item.kind for item in evidence.list_by_state(state_id)
    }


async def test_iterative_malformed_approval_signal_is_typed() -> None:
    """A matching approval signal with an invalid decision cannot escape the loop."""
    state_id = "malformed-approval-signal"
    request_id = _approval_request_id(state_id, "write-1", {"value": "raw"})
    model = ScriptedRoundModel(
        (
            (
                _tool_event("echo.write", {"value": "raw"}, "write-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    states = FakeStateRepository()
    items = await _run_durable(
        model,
        RunAgentInput(state_id=state_id, instruction="write"),
        states,
        FakeSignalRepository((_approval_signal(state_id, request_id, "unsupported"),)),
        FakeEvidenceRepository(),
    )

    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.code == "agent_approval_invalid"
    assert states.get(state_id).status is AgentStatus.FAILED


@pytest.mark.parametrize(
    ("agent_type", "expected_code"),
    [
        (StepLimitedProbeAgent, "agent_max_steps_exceeded"),
        (ToolLimitedProbeAgent, "agent_max_tool_calls_exceeded"),
    ],
)
async def test_iterative_runner_enforces_step_and_atomic_tool_limits(
    agent_type: type[_EchoToolAgentBase],
    expected_code: str,
) -> None:
    """Step는 request 전에, tool limit은 batch 전체 dispatch 전에 집행된다."""
    rounds = (
        (
            _tool_event("echo.read", {"value": "a"}, "a-1"),
            _tool_event("echo.read", {"value": "b"}, "b-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        ),
        (
            _tool_event("echo.read", {"value": "c"}, "c-1"),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        ),
    )
    model = ScriptedRoundModel(rounds)

    items = await _collect(
        _invoke_execute(
            agent_type(model),
            RunAgentInput(state_id=expected_code, instruction="loop"),
        )
    )

    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.code == expected_code
    if expected_code == "agent_max_tool_calls_exceeded":
        assert not any(isinstance(item.payload, Tool) for item in items)
        assert len(model.requests) == 1
    else:
        assert len(model.requests) == 2


@pytest.mark.parametrize(
    ("usage", "expected_code"),
    [
        (ModelUsage(total_tokens=6), "agent_max_tokens_exceeded"),
        (None, "agent_usage_unavailable"),
    ],
)
async def test_iterative_runner_enforces_provider_usage_budget(
    usage: ModelUsage | None,
    expected_code: str,
) -> None:
    """Token budget는 response usage 뒤 검사하고 missing usage는 fail closed 한다."""
    model = ScriptedRoundModel(
        ((ModelStreamEvent(kind=ModelStreamEventKind.DONE, usage=usage),),)
    )

    items = await _collect(
        _invoke_execute(
            TokenLimitedProbeAgent(model),
            RunAgentInput(state_id=expected_code, instruction="budget"),
        )
    )

    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.code == expected_code


@pytest.mark.parametrize("surface", ["run", "events"])
@pytest.mark.parametrize(
    ("usage", "expected_code", "expected_total"),
    [
        (ModelUsage(total_tokens=6), "agent_max_tokens_exceeded", 6),
        (None, "agent_usage_unavailable", 0),
    ],
)
async def test_iterative_usage_limit_terminal_preserves_route_and_evidence(
    surface: str,
    usage: ModelUsage | None,
    expected_code: str,
    expected_total: int,
) -> None:
    """Usage failures retain current routing, counters, usage, and model evidence."""
    state_id = f"usage-evidence-{surface}-{expected_code}"
    route: JsonObject = {
        "model_ref": "support/primary",
        "profile": "vllm-local",
        "provider": "openai",
        "model": "served-model",
    }
    model = ScriptedRoundModel(
        (
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.DONE,
                    usage=usage,
                    metadata=route,
                ),
            ),
        )
    )
    states = FakeStateRepository()
    evidence = FakeEvidenceRepository()
    target = DurableTokenLimitedProbeAgent(
        model,
        states,
        FakeSignalRepository(()),
        evidence,
    )
    runner = AgentRunner.for_agent_instance(target)
    command = RunAgentInput(state_id=state_id, instruction="budget")

    if surface == "events":
        events = [event async for event in runner.run_events(command)]
        terminal = events[-1]
        assert isinstance(terminal, RunFinishedEvent)
        assert terminal.error is not None
        terminal_metadata = terminal.error["metadata"]
        assert isinstance(terminal_metadata, Mapping)
        assert terminal.error["code"] == expected_code
    else:
        items = await _collect(runner.run(command))
        error = items[-1].payload
        assert isinstance(error, Error)
        assert error.code == expected_code
        terminal_metadata = error.metadata
    assert {key: terminal_metadata[key] for key in route} == route
    assert terminal_metadata["model_steps"] == 1
    assert terminal_metadata["total_tokens"] == expected_total
    usage_metadata = terminal_metadata["usage"]
    assert isinstance(usage_metadata, Mapping)
    assert usage_metadata.get("total_tokens") == (
        None if usage is None else usage.total_tokens
    )
    model_evidence = next(
        item
        for item in evidence.list_by_state(state_id)
        if item.kind is AgentEvidenceKind.MODEL
    )
    decision = cast(Mapping[str, JsonValue], model_evidence.payload["decision"])
    assert decision["routing"] == route
    error_evidence = cast(Mapping[str, JsonValue], decision["error"])
    assert error_evidence["code"] == expected_code
    assert states.get(state_id).status is AgentStatus.FAILED


async def test_iterative_runner_timeout_stops_hanging_model_and_durable_tool() -> None:
    """Wall-clock timeout은 hanging model과 async tool을 typed terminal로 중단한다."""
    stateless = await _collect(
        _invoke_execute(
            TimeoutProbeAgent(HangingModel()),
            RunAgentInput(state_id="timeout-model", instruction="wait"),
        )
    )
    stateless_error = stateless[-1].payload
    assert isinstance(stateless_error, Error)
    assert stateless_error.code == "agent_timeout"

    states = FakeStateRepository()
    durable_agent = DurableTimeoutProbeAgent(
        ScriptedRoundModel(
            (
                (
                    _tool_event("wait.forever", {}, "wait-1"),
                    ModelStreamEvent(kind=ModelStreamEventKind.DONE),
                ),
            )
        ),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )
    durable = await _collect(
        _invoke_execute(
            durable_agent,
            RunAgentInput(state_id="timeout-tool", instruction="wait"),
        )
    )
    durable_error = durable[-1].payload
    assert isinstance(durable_error, Error)
    assert durable_error.code == "agent_timeout"
    assert states.get("timeout-tool").status is AgentStatus.FAILED
    assert states.get("timeout-tool").transition is AgentStateTransition.TIMED_OUT
    assert states.get("timeout-tool").reason is AgentStateReason.TIMEOUT


@pytest.mark.parametrize("surface", ["run", "events"])
async def test_iterative_sync_tool_with_deadline_fails_before_dispatch(
    surface: str,
) -> None:
    """In-process sync sleep cannot claim enforceable timeout and never executes."""
    model = ScriptedRoundModel(
        (
            (
                _tool_event("sync.sleep", {}, "sleep-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    target = SyncTimeoutProbeAgent(model)
    runner = AgentRunner.for_agent_instance(target)
    command = RunAgentInput(state_id=f"sync-timeout-{surface}", instruction="sleep")

    if surface == "events":
        events = [event async for event in runner.run_events(command)]
        terminal = events[-1]
        assert isinstance(terminal, RunFinishedEvent)
        assert terminal.error is not None
        assert terminal.error["code"] == "agent_sync_tool_timeout_unenforceable"
        assert not any(isinstance(event, ToolCallResultEvent) for event in events)
    else:
        items = await _collect(runner.run(command))
        error = items[-1].payload
        assert isinstance(error, Error)
        assert error.code == "agent_sync_tool_timeout_unenforceable"
        assert not any(isinstance(item.payload, Tool) for item in items)
    assert target.called is False


async def test_guarded_complete_path_uses_same_iterative_tool_semantics() -> None:
    """NO_STREAM mode는 complete response tool batch 뒤 complete를 재호출한다."""
    model = ScriptedCompleteModel(
        (
            ModelResponse(
                content="calling",
                tool_calls=(
                    ModelToolCall("echo.read", {"value": "complete"}, "complete-1"),
                ),
            ),
            ModelResponse(content="guarded final"),
        )
    )

    items = await _collect(
        _invoke_execute(
            GuardedCompleteProbeAgent(model),
            RunAgentInput(state_id="complete-path", instruction="echo"),
        )
    )

    assert len(model.requests) == 2
    assert model.stream_calls == 0
    assert sum(item.kind is AgentYieldKind.TOOL for item in items) == 1
    assert sum(item.kind is AgentYieldKind.FINAL for item in items) == 1
    assert any(
        message.role is ModelMessageRole.TOOL for message in model.requests[1].messages
    )


@pytest.mark.parametrize("terminal_count", [0, 2])
async def test_iterative_runner_requires_exactly_one_done_and_one_final(
    terminal_count: int,
) -> None:
    """Missing/duplicate DONE는 success final을 만들지 않는다."""
    round_ = (
        ModelStreamEvent(kind=ModelStreamEventKind.TOKEN_DELTA, token_delta="partial"),
        *(
            ModelStreamEvent(kind=ModelStreamEventKind.DONE)
            for _ in range(terminal_count)
        ),
    )
    items = await _collect(
        _invoke_execute(
            ToollessProbeAgent(ScriptedRoundModel((round_,))),
            RunAgentInput(state_id=f"terminal-{terminal_count}", instruction="x"),
        )
    )

    assert sum(item.kind is AgentYieldKind.FINAL for item in items) == 0
    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.code == "agent_model_terminal_invalid"


async def test_iterative_run_events_have_unique_step_and_final_boundaries() -> None:
    """반복 model/tool steps는 unique ids와 한 RunFinished만 방출한다."""
    model = ScriptedRoundModel(
        (
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.MESSAGE_DELTA,
                    message_delta="planning",
                ),
                ModelStreamEvent(
                    kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
                    tool_call=ModelToolCall("echo.read", {"value": "x"}),
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.MESSAGE_DELTA,
                    message_delta="final",
                ),
                ModelStreamEvent(
                    kind=ModelStreamEventKind.DONE,
                    usage=ModelUsage(total_tokens=3),
                ),
            ),
        )
    )

    events = await _run_events_durable(
        model,
        RunAgentInput(state_id="events-iter", instruction="x"),
        FakeStateRepository(),
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    started = [
        event.step_name for event in events if isinstance(event, StepStartedEvent)
    ]
    finished = [
        event.step_name for event in events if isinstance(event, StepFinishedEvent)
    ]
    message_ids = {
        event.message_id for event in events if isinstance(event, MessageDeltaEvent)
    }
    assert started == ["model-1", "tool-1", "model-2"]
    assert finished == started
    assert message_ids == {
        "events-iter:model-1:message",
        "events-iter:model-2:message",
    }
    assert sum(isinstance(event, RunFinishedEvent) for event in events) == 1


@pytest.mark.parametrize("surface", ["run", "events"])
async def test_iterative_restart_requires_hitl_for_incomplete_non_idempotent_tool(
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    """Fresh runner never retries an incomplete non-idempotent tool boundary."""
    state_id = f"crash-{surface}"
    model = ScriptedRoundModel(
        (
            (
                _tool_event("external.write", {"value": "x"}, "external-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    evidence = FakeEvidenceRepository()
    first = NonIdempotentCrashProbeAgent(model, states, signals, evidence)

    async def crash_dispatch(
        self: AgentRunner,
        call: ModelToolCall,
        attribution: AgentEventAttribution,
    ) -> object:
        raise RuntimeError("simulated crash window")

    monkeypatch.setattr(AgentRunner, "_dispatch", crash_dispatch)
    with pytest.raises(RuntimeError):
        await _collect(
            _invoke_execute(
                first,
                RunAgentInput(state_id=state_id, instruction="write"),
            )
        )
    monkeypatch.undo()

    restarted = NonIdempotentCrashProbeAgent(model, states, signals, evidence)
    command = RunAgentInput(state_id=state_id, instruction="write", resume=True)
    if surface == "events":
        events = [
            event
            async for event in AgentRunner.for_agent_instance(restarted).run_events(
                command
            )
        ]
        assert isinstance(events[-1], RunPausedEvent)
        assert events[-1].reason is AgentStateReason.RECOVERY_REQUIRES_HITL
    else:
        items = await _collect(_invoke_execute(restarted, command))
        progress = items[-1].payload
        assert isinstance(progress, Progress)
        assert progress.message == "resume action: require_hitl"
    assert restarted.dispatched == 0
    assert len(model.requests) == 1


async def test_iterative_restart_reuses_call_bound_approval_after_dispatch_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A persisted approval authorizes only its unchanged pending retry call."""
    state_id = "approved-crash"
    arguments: dict[str, JsonValue] = {"value": "approved"}
    request_id = _approval_request_id(state_id, "write-1", arguments)
    model = ScriptedRoundModel(
        (
            (
                _tool_event("echo.write", arguments, "write-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (ModelStreamEvent(kind=ModelStreamEventKind.DONE),),
        )
    )
    states = FakeStateRepository()
    signals = FakeSignalRepository((_approval_signal(state_id, request_id, "approve"),))
    evidence = FakeEvidenceRepository()
    first = ProbeAgent(model, states, signals, evidence)

    async def crash_dispatch(
        self: AgentRunner,
        call: ModelToolCall,
        attribution: AgentEventAttribution,
    ) -> object:
        raise RuntimeError("simulated approved dispatch crash")

    monkeypatch.setattr(AgentRunner, "_dispatch", crash_dispatch)
    with pytest.raises(RuntimeError):
        await _collect(
            _invoke_execute(
                first,
                RunAgentInput(state_id=state_id, instruction="write"),
            )
        )
    monkeypatch.undo()

    restarted = ProbeAgent(model, states, signals, evidence)
    resumed = await _collect(
        _invoke_execute(
            restarted,
            RunAgentInput(state_id=state_id, instruction="write", resume=True),
        )
    )

    assert not any(isinstance(item.payload, Approval) for item in resumed)
    assert any(isinstance(item.payload, Tool) for item in resumed)
    assert resumed[-1].kind is AgentYieldKind.FINAL
    assert len(model.requests) == 2


async def test_iterative_resume_rejects_tampered_approved_pending_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changing only persisted pending args invalidates the approval fingerprint."""
    state_id = "approved-tamper"
    original_arguments: dict[str, JsonValue] = {"value": "approved"}
    request_id = _approval_request_id(state_id, "write-1", original_arguments)
    model = ScriptedRoundModel(
        (
            (
                _tool_event("echo.write", original_arguments, "write-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    states = FakeStateRepository()
    signals = FakeSignalRepository((_approval_signal(state_id, request_id, "approve"),))
    evidence = FakeEvidenceRepository()
    first = ProbeAgent(model, states, signals, evidence)

    async def crash_dispatch(
        self: AgentRunner,
        call: ModelToolCall,
        attribution: AgentEventAttribution,
    ) -> object:
        raise RuntimeError("simulated approved dispatch crash")

    monkeypatch.setattr(AgentRunner, "_dispatch", crash_dispatch)
    with pytest.raises(RuntimeError):
        await _collect(
            _invoke_execute(
                first,
                RunAgentInput(state_id=state_id, instruction="write"),
            )
        )
    monkeypatch.undo()

    current = states.get(state_id)
    checkpoint = cast(
        JsonObject,
        current.metadata[RUNNER_CHECKPOINT_METADATA_KEY],
    )
    pending = cast(Sequence[JsonValue], checkpoint["pending_calls"])
    persisted_call = cast(Mapping[str, JsonValue], pending[0])
    tampered_checkpoint: JsonObject = {
        **checkpoint,
        "pending_calls": [
            {**persisted_call, "arguments": {"value": "tampered"}},
            *pending[1:],
        ],
    }
    states.save(
        replace(
            current,
            metadata={
                **current.metadata,
                RUNNER_CHECKPOINT_METADATA_KEY: tampered_checkpoint,
            },
        )
    )

    resumed = await _run_durable(
        model,
        RunAgentInput(state_id=state_id, instruction="write", resume=True),
        states,
        signals,
        evidence,
    )

    approval = next(
        item.payload for item in resumed if isinstance(item.payload, Approval)
    )
    assert approval.id == _approval_request_id(
        state_id,
        "write-1",
        {"value": "tampered"},
    )
    assert not any(isinstance(item.payload, Tool) for item in resumed)
    assert AgentEvidenceKind.TOOL not in {
        item.kind for item in evidence.list_by_state(state_id)
    }
    assert len(model.requests) == 1


@pytest.mark.parametrize("surface", ["run", "events"])
async def test_iterative_restored_pending_validation_failure_is_typed(
    surface: str,
) -> None:
    """A structurally valid checkpoint with an unknown pending tool fails closed."""
    state_id = f"invalid-pending-{surface}"
    model = ScriptedRoundModel(
        (
            (
                _tool_event("echo.write", {"value": "draft"}, "write-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    evidence = FakeEvidenceRepository()
    paused = await _run_durable(
        model,
        RunAgentInput(state_id=state_id, instruction="write"),
        states,
        signals,
        evidence,
    )
    assert any(isinstance(item.payload, Approval) for item in paused)
    current = states.get(state_id)
    checkpoint = cast(JsonObject, current.metadata[RUNNER_CHECKPOINT_METADATA_KEY])
    pending = cast(Sequence[JsonValue], checkpoint["pending_calls"])
    persisted_call = cast(Mapping[str, JsonValue], pending[0])
    invalid_checkpoint: JsonObject = {
        **checkpoint,
        "pending_calls": [{**persisted_call, "name": "missing.tool"}],
    }
    states.save(
        replace(
            current,
            metadata={
                **current.metadata,
                RUNNER_CHECKPOINT_METADATA_KEY: invalid_checkpoint,
            },
        )
    )
    runner = AgentRunner.for_agent_instance(
        ProbeAgent(model, states, signals, evidence)
    )
    command = RunAgentInput(state_id=state_id, instruction="write", resume=True)

    if surface == "events":
        events = [event async for event in runner.run_events(command)]
        terminal = events[-1]
        assert isinstance(terminal, RunFinishedEvent)
        assert terminal.error is not None
        assert terminal.error["code"] == "agent_checkpoint_invalid"
    else:
        items = await _collect(runner.run(command))
        error = items[-1].payload
        assert isinstance(error, Error)
        assert error.code == "agent_checkpoint_invalid"
    assert states.get(state_id).status is AgentStatus.FAILED
    assert AgentEvidenceKind.TOOL not in {
        item.kind for item in evidence.list_by_state(state_id)
    }
    assert len(model.requests) == 1


async def test_iterative_multi_approval_batch_progresses_across_resumes() -> None:
    """Each approved fingerprint persists while the whole batch remains atomic."""
    state_id = "multi-approval"
    first_arguments: dict[str, JsonValue] = {"value": "first"}
    second_arguments: dict[str, JsonValue] = {"value": "second"}
    model = ScriptedRoundModel(
        (
            (
                _tool_event("echo.write", first_arguments, "write-1"),
                _tool_event("echo.write", second_arguments, "write-2"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (ModelStreamEvent(kind=ModelStreamEventKind.DONE),),
        )
    )
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    evidence = FakeEvidenceRepository()

    first_pause = await _run_durable(
        model,
        RunAgentInput(state_id=state_id, instruction="write twice"),
        states,
        signals,
        evidence,
    )
    first_approval = next(
        item.payload for item in first_pause if isinstance(item.payload, Approval)
    )
    signals.append(_approval_signal(state_id, first_approval.id, "approve"))

    second_pause = await _run_durable(
        model,
        RunAgentInput(
            state_id=state_id,
            instruction="write twice",
            resume=True,
        ),
        states,
        signals,
        evidence,
    )
    second_approval = [
        item.payload for item in second_pause if isinstance(item.payload, Approval)
    ][-1]
    assert second_approval.id == _approval_request_id(
        state_id,
        "write-2",
        second_arguments,
    )
    assert not any(
        isinstance(item.payload, Tool) for item in first_pause + second_pause
    )
    signals.append(_approval_signal(state_id, second_approval.id, "approve"))

    completed = await _run_durable(
        model,
        RunAgentInput(
            state_id=state_id,
            instruction="write twice",
            resume=True,
        ),
        states,
        signals,
        evidence,
    )

    assert [
        item.payload.arguments["value"]
        for item in completed
        if isinstance(item.payload, Tool)
    ] == ["first", "second"]
    assert completed[-1].kind is AgentYieldKind.FINAL
    assert len(model.requests) == 2


async def test_iterative_malformed_approval_plan_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An incomplete authority plan cannot reach tool dispatch."""
    monkeypatch.setattr(
        runner_module,
        "plan_agent_tool_approval",
        lambda **_kwargs: AgentApprovalPlan(
            action=AgentApprovalPlanAction.WAIT_FOR_APPROVAL
        ),
    )
    model = ScriptedRoundModel(
        (
            (
                _tool_event("echo.write", {"value": "x"}, "write-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    items = await _run_durable(
        model,
        RunAgentInput(state_id="invalid-approval-plan", instruction="write"),
        FakeStateRepository(),
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.code == "agent_approval_invalid"
    assert not any(isinstance(item.payload, Tool) for item in items)


async def test_iterative_cancellation_after_tool_prevents_result_and_final() -> None:
    """Tool return 직후 cancel poll은 result commit과 next model을 중단한다."""
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    agent = CancelDuringToolProbeAgent(
        ScriptedRoundModel(
            (
                (
                    _tool_event("cancel.after", {}, "cancel-call"),
                    ModelStreamEvent(kind=ModelStreamEventKind.DONE),
                ),
            )
        ),
        states,
        signals,
        FakeEvidenceRepository(),
    )

    items = await _collect(
        _invoke_execute(
            agent,
            RunAgentInput(state_id="cancel-tool", instruction="cancel"),
        )
    )

    assert any(isinstance(item.payload, Cancel) for item in items)
    assert not any(isinstance(item.payload, Tool) for item in items)
    assert not any(item.kind is AgentYieldKind.FINAL for item in items)
    assert states.get("cancel-tool").status is AgentStatus.CANCELLED

    event_states = FakeStateRepository()
    event_signals = FakeSignalRepository(())
    event_agent = CancelDuringToolProbeAgent(
        ScriptedRoundModel(
            (
                (
                    _tool_event("cancel.after", {}, "cancel-event-call"),
                    ModelStreamEvent(kind=ModelStreamEventKind.DONE),
                ),
            )
        ),
        event_states,
        event_signals,
        FakeEvidenceRepository(),
    )
    events = [
        event
        async for event in AgentRunner.for_agent_instance(event_agent).run_events(
            RunAgentInput(state_id="cancel-tool", instruction="cancel")
        )
    ]
    assert isinstance(events[-1], RunFinishedEvent)
    assert events[-1].error == {
        "code": "cancelled",
        "message": "cancel after dispatch",
        "metadata": {
            "state": AgentStatus.CANCELLED.value,
            "signal_id": "cancel:during-tool",
            "requested_by": "tester",
        },
    }
    assert sum(isinstance(event, RunFinishedEvent) for event in events) == 1
    assert not any(isinstance(event, ToolCallResultEvent) for event in events)


@pytest.mark.parametrize("surface", ["run", "events"])
async def test_iterative_signal_arriving_during_tool_has_surface_parity(
    surface: str,
) -> None:
    """Post-tool safe boundary consumes and exposes the same USER_MESSAGE signal."""
    state_id = f"signal-tool-{surface}"
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    evidence = FakeEvidenceRepository()
    model = ScriptedRoundModel(
        (
            (
                _tool_event("signal.after", {"state_id": state_id}, "signal-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (ModelStreamEvent(kind=ModelStreamEventKind.DONE),),
        )
    )
    target = SignalDuringToolProbeAgent(model, states, signals, evidence)
    runner = AgentRunner.for_agent_instance(target)
    command = RunAgentInput(state_id=state_id, instruction="signal")

    if surface == "events":
        outputs: Sequence[AgentEvent | AgentYield[object]] = [
            event async for event in runner.run_events(command)
        ]
        progress_index = next(
            index
            for index, item in enumerate(outputs)
            if isinstance(item, ArtifactEvent) and item.name == "signal_progress"
        )
        result_index = next(
            index
            for index, item in enumerate(outputs)
            if isinstance(item, ToolCallResultEvent)
        )
    else:
        outputs = await _collect(runner.run(command))
        progress_index = next(
            index
            for index, item in enumerate(outputs)
            if isinstance(item, AgentYield)
            and isinstance(item.payload, Progress)
            and item.payload.current_step == "signal"
        )
        result_index = next(
            index
            for index, item in enumerate(outputs)
            if isinstance(item, AgentYield) and isinstance(item.payload, Tool)
        )
    assert progress_index < result_index
    assert signals.list_pending(state_id) == ()
    assert AgentEvidenceKind.SIGNAL in {
        item.kind for item in evidence.list_by_state(state_id)
    }


@pytest.mark.parametrize("surface", ["run", "events"])
async def test_iterative_cancellation_before_first_batch_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    """A cancel arriving after authority validation still prevents all dispatch."""
    state_id = f"cancel-before-{surface}"
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    model = ScriptedRoundModel(
        (
            (
                _tool_event("echo.read", {"value": "x"}, "read-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    target = ProbeAgent(model, states, signals, FakeEvidenceRepository())
    original = AgentRunner._authorize_pending_batch

    def authorize_and_cancel(
        self: AgentRunner,
        state: AgentState | None,
        context: runner_module._ExecutionContext,
    ) -> runner_module._AuthorizationResult:
        outcome = original(self, state, context)
        signals.append(
            AgentSignal(
                id=f"cancel:{surface}",
                agent_state_id=state_id,
                kind=AgentSignalKind.CANCEL,
                payload={"reason": "cancel before dispatch"},
            )
        )
        return outcome

    monkeypatch.setattr(AgentRunner, "_authorize_pending_batch", authorize_and_cancel)
    runner = AgentRunner.for_agent_instance(target)
    command = RunAgentInput(state_id=state_id, instruction="cancel")
    if surface == "events":
        outputs: Sequence[AgentEvent | AgentYield[object]] = [
            event async for event in runner.run_events(command)
        ]
        assert isinstance(outputs[-1], RunFinishedEvent)
    else:
        outputs = await _collect(runner.run(command))
        assert any(
            isinstance(item, AgentYield) and isinstance(item.payload, Cancel)
            for item in outputs
        )
    assert not any(isinstance(item, ToolCallResultEvent) for item in outputs)
    assert states.get(state_id).status is AgentStatus.CANCELLED


@pytest.mark.parametrize("surface", ["run", "events"])
async def test_iterative_tool_lifecycle_failure_stops_before_next_model(
    surface: str,
) -> None:
    """A non-active durable state observed after dispatch terminates the loop."""
    state_id = f"tool-state-failed-{surface}"
    states = FakeStateRepository()
    model = ScriptedRoundModel(
        (
            (
                _tool_event("lifecycle.fail", {"state_id": state_id}, "fail-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    agent = LifecycleMutatingToolProbeAgent(
        model,
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    runner = AgentRunner.for_agent_instance(agent)
    command = RunAgentInput(state_id=state_id, instruction="fail")
    if surface == "events":
        events = [event async for event in runner.run_events(command)]
        terminal = events[-1]
        assert isinstance(terminal, RunFinishedEvent)
        assert terminal.error is not None
        assert terminal.error["code"] == AgentStateReason.EXECUTION_FAILED.value
    else:
        items = await _collect(runner.run(command))
        error = items[-1].payload
        assert isinstance(error, Error)
        assert error.code == AgentStateReason.EXECUTION_FAILED.value
    assert len(model.requests) == 1


@pytest.mark.parametrize("surface", ["run", "events"])
@pytest.mark.parametrize("guarded", [False, True])
async def test_iterative_framework_model_errors_are_typed_terminals(
    surface: str,
    guarded: bool,
) -> None:
    """Framework failures from stream/complete become one durable typed terminal."""
    state_id = f"framework-model-{surface}-{guarded}"
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    evidence = FakeEvidenceRepository()
    model = FrameworkFailingModel()
    target: object = (
        DurableGuardedFrameworkProbeAgent(model, states, signals, evidence)
        if guarded
        else ProbeAgent(model, states, signals, evidence)
    )
    runner = AgentRunner.for_agent_instance(target)
    command = RunAgentInput(state_id=state_id, instruction="fail")

    if surface == "events":
        outputs = [event async for event in runner.run_events(command)]
        terminal = [event for event in outputs if isinstance(event, RunFinishedEvent)]
        assert len(terminal) == 1
        assert terminal[0].error is not None
        assert terminal[0].error["code"] == "agent_model_execution_failed"
    else:
        items = await _collect(runner.run(command))
        terminal_items = [item for item in items if item.kind is AgentYieldKind.ERROR]
        assert len(terminal_items) == 1
        error = terminal_items[0].payload
        assert isinstance(error, Error)
        assert error.code == "agent_model_execution_failed"
        assert not any(item.kind is AgentYieldKind.FINAL for item in items)
    assert states.get(state_id).status is AgentStatus.FAILED
    assert states.get(state_id).reason is AgentStateReason.EXECUTION_FAILED


@pytest.mark.parametrize("surface", ["run", "events"])
@pytest.mark.parametrize("tool_name", ["framework.raise", "framework.bad_result"])
async def test_iterative_framework_tool_errors_are_typed_terminals(
    surface: str,
    tool_name: str,
) -> None:
    """Tool invocation and result serialization failures never escape generators."""
    state_id = f"framework-tool-{surface}-{tool_name}"
    states = FakeStateRepository()
    model = ScriptedRoundModel(
        (
            (
                _tool_event(tool_name, {}, "tool-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    target = FrameworkFailingToolProbeAgent(
        model,
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )
    runner = AgentRunner.for_agent_instance(target)
    command = RunAgentInput(state_id=state_id, instruction="fail")

    if surface == "events":
        outputs = [event async for event in runner.run_events(command)]
        terminal = [event for event in outputs if isinstance(event, RunFinishedEvent)]
        assert len(terminal) == 1
        assert terminal[0].error is not None
        assert terminal[0].error["code"] == "agent_tool_execution_failed"
    else:
        items = await _collect(runner.run(command))
        errors = [item.payload for item in items if isinstance(item.payload, Error)]
        assert len(errors) == 1
        assert errors[0].code == "agent_tool_execution_failed"
        assert not any(item.kind is AgentYieldKind.FINAL for item in items)
    assert states.get(state_id).status is AgentStatus.FAILED
    assert states.get(state_id).reason is AgentStateReason.EXECUTION_FAILED


async def test_iterative_run_events_stateless_approval_fails_closed() -> None:
    """Durable authority port가 없는 event path는 risky tool을 실행하지 않는다."""
    model = ScriptedRoundModel(
        (
            (
                _tool_event("echo.write", {"value": "x"}, "write-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    target = ProbeAgent(
        model,
        FakeStateRepository(),
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )
    runner = AgentRunner(agent=Agent.get(ProbeAgent), target=target, model=model)

    events = [
        event
        async for event in runner.run_events(
            RunAgentInput(state_id="stateless-approval", instruction="write")
        )
    ]

    finished = events[-1]
    assert isinstance(finished, RunFinishedEvent)
    assert finished.error is not None
    assert finished.error["code"] == "agent_approval_unavailable"
    assert not any(isinstance(event, ToolCallResultEvent) for event in events)


async def test_iterative_run_events_enforces_model_timeout_and_step_limit() -> None:
    """Neutral event path도 timeout과 next-request step limit을 terminalize한다."""
    timeout_events = [
        event
        async for event in AgentRunner.for_agent_instance(
            TimeoutProbeAgent(HangingModel())
        ).run_events(RunAgentInput(state_id="event-timeout", instruction="wait"))
    ]
    timeout_finished = timeout_events[-1]
    assert isinstance(timeout_finished, RunFinishedEvent)
    assert timeout_finished.error is not None
    assert timeout_finished.error["code"] == "agent_timeout"

    step_model = ScriptedRoundModel(
        (
            (
                _tool_event("echo.read", {"value": "a"}, "a"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (
                _tool_event("echo.read", {"value": "b"}, "b"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    step_events = [
        event
        async for event in AgentRunner.for_agent_instance(
            StepLimitedProbeAgent(step_model)
        ).run_events(RunAgentInput(state_id="event-step", instruction="loop"))
    ]
    step_finished = step_events[-1]
    assert isinstance(step_finished, RunFinishedEvent)
    assert step_finished.error is not None
    assert step_finished.error["code"] == "agent_max_steps_exceeded"


async def test_iterative_tool_policy_timeout_without_run_deadline() -> None:
    """Tool-specific deadline also cancels a hanging async dispatch."""
    model = ScriptedRoundModel(
        (
            (
                _tool_event("wait.policy", {}, "wait-policy"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    items = await _collect(
        _invoke_execute(
            ToolPolicyTimeoutProbeAgent(model),
            RunAgentInput(state_id="tool-policy-timeout", instruction="wait"),
        )
    )
    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.code == "agent_timeout"

    event_model = ScriptedRoundModel(
        (
            (
                _tool_event("wait.policy", {}, "wait-policy-event"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
        )
    )
    events = [
        event
        async for event in AgentRunner.for_agent_instance(
            ToolPolicyTimeoutProbeAgent(event_model)
        ).run_events(
            RunAgentInput(state_id="tool-policy-event-timeout", instruction="wait")
        )
    ]
    finished = events[-1]
    assert isinstance(finished, RunFinishedEvent)
    assert finished.error is not None
    assert finished.error["code"] == "agent_timeout"


@pytest.mark.parametrize(
    "calls",
    [
        (
            ModelToolCall("echo.read", {"value": "a"}, "duplicate"),
            ModelToolCall("echo.read", {"value": "b"}, "duplicate"),
        ),
        (ModelToolCall("echo.read", {"value": "a"}, " "),),
    ],
)
async def test_iterative_runner_rejects_blank_or_duplicate_call_ids(
    calls: tuple[ModelToolCall, ...],
) -> None:
    """Provider correlation ids are nonblank and unique before dispatch."""
    round_ = tuple(
        ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
            tool_call=call,
        )
        for call in calls
    ) + (ModelStreamEvent(kind=ModelStreamEventKind.DONE),)
    items = await _collect(
        _invoke_execute(
            StatelessProbeAgent(ScriptedRoundModel((round_,))),
            RunAgentInput(state_id="bad-call-ids", instruction="x"),
        )
    )
    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.code == "agent_tool_batch_invalid"


async def test_guarded_complete_structured_output_uses_one_final() -> None:
    """Complete structured payload channel does not duplicate the public final."""
    model = ScriptedCompleteModel(
        (ModelResponse(content="", structured_output={"ok": True}),)
    )
    items = await _collect(
        _invoke_execute(
            GuardedCompleteProbeAgent(model),
            RunAgentInput(state_id="complete-structured", instruction="x"),
        )
    )
    assert sum(item.kind is AgentYieldKind.FINAL for item in items) == 1


async def test_iterative_resume_without_checkpoint_starts_from_input() -> None:
    """A legacy active state with no loop checkpoint resumes without replay data."""
    state_id = "resume-without-checkpoint"
    states = FakeStateRepository()
    states.save(
        AgentState(
            id=state_id,
            agent_type="runner_probe",
            status=AgentStatus.ACTIVE,
            transition=AgentStateTransition.RUNNING,
        )
    )
    model = ScriptedRoundModel(((ModelStreamEvent(kind=ModelStreamEventKind.DONE),),))

    items = await _run_durable(
        model,
        RunAgentInput(state_id=state_id, instruction="resume", resume=True),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert items[-1].kind is AgentYieldKind.FINAL
    assert len(model.requests) == 1


@pytest.mark.parametrize("surface", ["run", "events"])
async def test_iterative_resume_rejects_non_mapping_checkpoint(surface: str) -> None:
    """A malformed checkpoint root cannot silently restart and replay actions."""
    state_id = "invalid-checkpoint-root"
    states = FakeStateRepository()
    states.save(
        AgentState(
            id=state_id,
            agent_type="runner_probe",
            status=AgentStatus.ACTIVE,
            metadata={RUNNER_CHECKPOINT_METADATA_KEY: []},
        )
    )
    agent = ProbeAgent(
        ScriptedRoundModel(()),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    runner = AgentRunner.for_agent_instance(agent)
    command = RunAgentInput(state_id=state_id, instruction="resume", resume=True)
    if surface == "events":
        events = [event async for event in runner.run_events(command)]
        terminal = events[-1]
        assert isinstance(terminal, RunFinishedEvent)
        assert terminal.error is not None
        assert terminal.error["code"] == "agent_checkpoint_invalid"
    else:
        items = await _collect(runner.run(command))
        error = items[-1].payload
        assert isinstance(error, Error)
        assert error.code == "agent_checkpoint_invalid"
    assert states.get(state_id).status is AgentStatus.FAILED
    assert states.get(state_id).reason is AgentStateReason.EXECUTION_FAILED


@pytest.mark.parametrize(
    ("key", "invalid_value"),
    [
        ("history", "not-a-sequence"),
        ("history", ["not-a-message"]),
        ("history", [{"role": 1, "content": "x", "metadata": {}}]),
        ("history", [{"role": "user", "content": "x", "metadata": []}]),
        ("history", [{"role": "invalid", "content": "x", "metadata": {}}]),
        ("assistant_text", {}),
        ("assistant_text", [1]),
        ("pending_calls", [{"name": 1, "arguments": {}}]),
        (
            "pending_calls",
            [{"name": "echo.read", "arguments": {}, "call_id": 1}],
        ),
        (
            "pending_calls",
            [{"name": "echo.read", "arguments": {}, "metadata": []}],
        ),
        ("route_metadata", []),
        ("step_count", True),
        ("static_context_fingerprint", 1),
    ],
)
async def test_iterative_resume_rejects_corrupted_checkpoint_fields(
    key: str,
    invalid_value: JsonValue,
) -> None:
    """Each persisted transcript/counter field is typed before resume execution."""
    state_id = f"invalid-checkpoint-{key}"
    checkpoint: dict[str, JsonValue] = {
        "history": [{"role": "user", "content": "x", "metadata": {}}],
        "assistant_text": [],
        "tool_calls": [],
        "step_count": 0,
        "tool_call_count": 0,
        "total_tokens": 0,
        "seen_call_ids": [],
        "approved_call_fingerprints": [],
        "pending_calls": [],
        "route_metadata": {},
    }
    checkpoint[key] = invalid_value
    states = FakeStateRepository()
    states.save(
        AgentState(
            id=state_id,
            agent_type="runner_probe",
            status=AgentStatus.ACTIVE,
            metadata={RUNNER_CHECKPOINT_METADATA_KEY: checkpoint},
        )
    )
    agent = ProbeAgent(
        ScriptedRoundModel(()),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    items = await _collect(
        _invoke_execute(
            agent,
            RunAgentInput(state_id=state_id, instruction="resume", resume=True),
        )
    )
    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.code == "agent_checkpoint_invalid"
    assert states.get(state_id).status is AgentStatus.FAILED


@pytest.mark.parametrize(
    "status",
    [AgentStatus.INTERRUPTED, AgentStatus.FAILED],
)
async def test_iterative_model_step_observes_external_terminal_state(
    monkeypatch: pytest.MonkeyPatch,
    status: AgentStatus,
) -> None:
    """A durable state transition at the model boundary stops success finalization."""
    original = AgentRunner._finish_model_step

    def finish_and_transition(
        self: AgentRunner,
        run_input: RunAgentInput,
        state: AgentState | None,
        context: runner_module._ExecutionContext,
        accumulator: runner_module._ModelStepAccumulator,
    ) -> ModelError | None:
        error = original(self, run_input, state, context, accumulator)
        if state is not None:
            current = self._states_required().get(state.id)
            self._states_required().save(
                replace(
                    current,
                    status=status,
                    transition=(
                        AgentStateTransition.INTERRUPTED
                        if status is AgentStatus.INTERRUPTED
                        else AgentStateTransition.FAILED
                    ),
                    reason=(
                        AgentStateReason.USER_INTERRUPTED
                        if status is AgentStatus.INTERRUPTED
                        else AgentStateReason.EXECUTION_FAILED
                    ),
                    current_activity="external model-boundary transition",
                )
            )
        return error

    monkeypatch.setattr(AgentRunner, "_finish_model_step", finish_and_transition)
    items = await _run_durable(
        ScriptedRoundModel(((ModelStreamEvent(kind=ModelStreamEventKind.DONE),),)),
        RunAgentInput(state_id=f"model-state-{status.value}", instruction="stop"),
        FakeStateRepository(),
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )

    assert not any(item.kind is AgentYieldKind.FINAL for item in items)
    assert any(item.kind is AgentYieldKind.ERROR for item in items) is (
        status is AgentStatus.FAILED
    )


async def test_iterative_event_cursor_correlates_missing_start_id() -> None:
    """Missing provider start/id still correlates args and end within one model step."""
    call = ModelToolCall("echo.read", {"value": "x"})
    model = ScriptedRoundModel(
        (
            (
                ModelStreamEvent(
                    kind=ModelStreamEventKind.TOOL_CALL_ARGS_DELTA,
                    tool_call=call,
                    tool_call_args_delta='{"value":"x"}',
                ),
                ModelStreamEvent(
                    kind=ModelStreamEventKind.TOOL_CALL_END,
                    tool_call=call,
                ),
                ModelStreamEvent(
                    kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
                    tool_call=call,
                ),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (ModelStreamEvent(kind=ModelStreamEventKind.DONE),),
        )
    )
    events = [
        event
        async for event in AgentRunner.for_agent_instance(
            StatelessProbeAgent(model)
        ).run_events(RunAgentInput(state_id="cursor-missing", instruction="x"))
    ]
    args = next(event for event in events if isinstance(event, ToolCallArgsDeltaEvent))
    end = next(event for event in events if isinstance(event, ToolCallEndEvent))
    result = next(event for event in events if isinstance(event, ToolCallResultEvent))
    assert (
        args.call_id == end.call_id == result.call_id == "cursor-missing:model-1:call-1"
    )


def test_iterative_arguments_digest_rejects_non_json_values() -> None:
    """Approval identity cannot be computed from non-deterministic arguments."""
    with pytest.raises(AgentDefinitionError, match="deterministic JSON"):
        _arguments_digest(cast(JsonObject, {"invalid": object()}))


def test_iterative_approved_call_requires_corresponding_assistant_history() -> None:
    """Approval modification cannot update an unrelated assistant call envelope."""
    history = (
        ModelMessage(ModelMessageRole.USER, "before"),
        ModelMessage(
            ModelMessageRole.ASSISTANT,
            "calling",
            metadata={
                "tool_calls": [{"id": "other", "name": "echo.write", "arguments": {}}]
            },
        ),
    )
    with pytest.raises(AgentDefinitionError, match="missing the approved tool call"):
        _history_with_approved_call(
            history,
            ModelToolCall("echo.write", {"value": "approved"}, "write-1"),
        )


async def test_agent_runner_wires_static_context_directly_into_model_request() -> None:
    """Static inbound packs reach ModelRequest context without prompt concatenation."""
    pack = ContextPack(
        id="static-1",
        content="static context",
        source="input:test",
        role=ContextPackRole.EVIDENCE,
    )
    model = RecordingModel((ModelStreamEvent(kind=ModelStreamEventKind.DONE),))

    await _collect(
        _invoke_execute(
            StatelessProbeAgent(model),
            RunAgentInput(
                state_id="static-context",
                instruction="answer",
                context=AgentContext(packs=(pack,)),
            ),
        )
    )

    request = model.requests[0]
    assert request.context == (pack,)
    assert request.context_manifest is not None
    assert request.context_manifest.entries[0].pack_id == "static-1"
    assert all(message.content != "static context" for message in request.messages)


@pytest.mark.parametrize(
    ("agent_type", "expected_calls", "expected_second_pack"),
    [
        (ContextProbeAgent, [1], "dynamic-1"),
        (RefreshingContextProbeAgent, [1, 2], "dynamic-2"),
    ],
)
async def test_agent_runner_context_provider_cache_and_refresh_semantics(
    agent_type: type[_ContextProbeBase],
    expected_calls: list[int],
    expected_second_pack: str,
) -> None:
    """Default context caches once; refresh_context_each_step calls every step."""
    contexts = (
        AgentContext(
            packs=(
                ContextPack(
                    id="dynamic-1",
                    content="first dynamic",
                    source="provider:test",
                    role=ContextPackRole.STATE,
                ),
            )
        ),
        AgentContext(
            packs=(
                ContextPack(
                    id="dynamic-2",
                    content="second dynamic",
                    source="provider:test",
                    role=ContextPackRole.STATE,
                ),
            )
        ),
    )
    provider = RecordingContextProvider(contexts)
    model = ScriptedRoundModel(
        (
            (
                _tool_event("context.echo", {"value": "x"}, "context-call"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (ModelStreamEvent(kind=ModelStreamEventKind.DONE),),
        )
    )
    states = FakeStateRepository()
    evidence = FakeEvidenceRepository()
    target = agent_type(
        model,
        provider,
        states,
        FakeSignalRepository(()),
        evidence,
    )

    items = await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(state_id="dynamic-context", instruction="answer")
        )
    )

    assert items[-1].kind is AgentYieldKind.FINAL
    assert provider.calls == expected_calls
    assert model.requests[0].context[0].id == "dynamic-1"
    assert model.requests[1].context[0].id == expected_second_pack
    context_evidence = [
        item
        for item in evidence.list_by_state("dynamic-context")
        if item.kind
        in (
            AgentEvidenceKind.CONTEXT,
            AgentEvidenceKind.CONTEXT_MANIFEST,
            AgentEvidenceKind.CONTEXT_DIGEST,
        )
    ]
    assert len(context_evidence) == 4
    assert all(item.summary is None for item in context_evidence)
    assert all("first dynamic" not in repr(item.payload) for item in context_evidence)
    assert all("second dynamic" not in repr(item.payload) for item in context_evidence)
    assert not any(
        item.kind is AgentEvidenceKind.CONTEXT_DIGEST for item in context_evidence
    )


async def test_agent_runner_fresh_resume_obtains_provider_context_again() -> None:
    """A resumed invocation restores no raw context cache and calls step 2 anew."""
    provider = RecordingContextProvider(
        (
            AgentContext(
                packs=(
                    ContextPack(
                        "resume-context-1",
                        "first",
                        "provider",
                        ContextPackRole.STATE,
                    ),
                )
            ),
            AgentContext(
                packs=(
                    ContextPack(
                        "resume-context-2",
                        "second",
                        "provider",
                        ContextPackRole.STATE,
                    ),
                )
            ),
        )
    )
    model = ScriptedRoundModel(
        (
            (
                _tool_event("context.write", {"value": "x"}, "write-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (ModelStreamEvent(kind=ModelStreamEventKind.DONE),),
        )
    )
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    evidence = FakeEvidenceRepository()
    target = ContextProbeAgent(model, provider, states, signals, evidence)

    paused = await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(state_id="context-resume", instruction="write")
        )
    )
    approval = next(
        item.payload for item in paused if isinstance(item.payload, Approval)
    )
    checkpoint = states.get("context-resume").metadata[RUNNER_CHECKPOINT_METADATA_KEY]
    assert "first" not in repr(checkpoint)
    assert "resume-context-1" not in repr(checkpoint)
    signals.append(_approval_signal("context-resume", approval.id, "approve"))
    resumed = await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(
                state_id="context-resume",
                instruction="write",
                resume=True,
            )
        )
    )

    assert resumed[-1].kind is AgentYieldKind.FINAL
    assert provider.calls == [1, 2]
    assert model.requests[1].context[0].id == "resume-context-2"
    kinds = [
        item.kind
        for item in evidence.list_by_state("context-resume")
        if item.kind in (AgentEvidenceKind.CONTEXT, AgentEvidenceKind.CONTEXT_MANIFEST)
    ]
    assert kinds.count(AgentEvidenceKind.CONTEXT) == 2
    assert kinds.count(AgentEvidenceKind.CONTEXT_MANIFEST) == 2


@pytest.mark.parametrize(
    ("resupply", "surface"),
    [
        ("same", "run"),
        ("missing", "run"),
        ("different", "run"),
        ("additive", "run"),
        ("different", "events"),
    ],
)
async def test_agent_runner_resume_requires_identical_static_context_resupply(
    resupply: str,
    surface: str,
) -> None:
    """Approval resume validates only a safe static-context fingerprint marker."""
    original_pack = ContextPack(
        "static-resume",
        "static-content-1",
        "caller",
        ContextPackRole.TASK,
    )
    original_context = AgentContext(packs=(original_pack,))
    provider = RecordingContextProvider((AgentContext(),))
    model = ScriptedRoundModel(
        (
            (
                _tool_event("context.write", {"value": "x"}, "write-1"),
                ModelStreamEvent(kind=ModelStreamEventKind.DONE),
            ),
            (ModelStreamEvent(kind=ModelStreamEventKind.DONE),),
        )
    )
    states = FakeStateRepository()
    signals = FakeSignalRepository(())
    state_id = f"static-resume-{resupply}-{surface}"
    target = ContextProbeAgent(
        model,
        provider,
        states,
        signals,
        FakeEvidenceRepository(),
    )

    paused = await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(
                state_id=state_id,
                instruction="write",
                context=original_context,
            )
        )
    )
    approval = next(
        item.payload for item in paused if isinstance(item.payload, Approval)
    )
    checkpoint = states.get(state_id).metadata[RUNNER_CHECKPOINT_METADATA_KEY]
    assert isinstance(checkpoint, Mapping)
    assert "static-resume" not in repr(checkpoint)
    assert "static-content-1" not in repr(checkpoint)
    assert "static_context_fingerprint" in checkpoint
    signals.append(_approval_signal(state_id, approval.id, "approve"))
    resume_context = (
        original_context
        if resupply == "same"
        else AgentContext()
        if resupply == "missing"
        else AgentContext(packs=(replace(original_pack, content="static-content-2"),))
        if resupply == "different"
        else AgentContext(
            packs=(
                original_pack,
                ContextPack(
                    "static-additive",
                    "extra",
                    "caller",
                    ContextPackRole.TASK,
                ),
            )
        )
    )
    command = RunAgentInput(
        state_id=state_id,
        instruction="write",
        resume=True,
        context=resume_context,
    )
    runner = AgentRunner.for_agent_instance(target)
    resumed: Sequence[AgentYield[object] | AgentEvent] = (
        [event async for event in runner.run_events(command)]
        if surface == "events"
        else await _collect(runner.run(command))
    )

    if resupply == "same":
        terminal = resumed[-1]
        assert isinstance(terminal, AgentYield)
        assert terminal.kind is AgentYieldKind.FINAL
        assert provider.calls == [1, 2]
        assert [request.context[0].content for request in model.requests] == [
            "static-content-1",
            "static-content-1",
        ]
    else:
        if surface == "events":
            terminal = resumed[-1]
            assert isinstance(terminal, RunFinishedEvent)
            assert terminal.error is not None
            assert terminal.error["code"] == "agent_checkpoint_invalid"
        else:
            terminal = resumed[-1]
            assert isinstance(terminal, AgentYield)
            error = terminal.payload
            assert isinstance(error, Error)
            assert error.code == "agent_checkpoint_invalid"
        assert len(model.requests) == 1
        assert not any(
            isinstance(item, AgentYield) and isinstance(item.payload, Tool)
            for item in resumed
        )


async def test_agent_runner_same_step_retry_deduplicates_context_evidence() -> None:
    """Fresh retry reacquires context but does not duplicate safe step evidence."""
    provider = RecordingContextProvider(
        (
            AgentContext(
                packs=(
                    ContextPack(
                        "retry-context",
                        "raw retry context",
                        "provider",
                        ContextPackRole.STATE,
                    ),
                )
            ),
        )
    )
    model = CrashThenDoneModel()
    states = FakeStateRepository()
    evidence = FakeEvidenceRepository()
    target = ContextProbeAgent(
        model,
        provider,
        states,
        FakeSignalRepository(()),
        evidence,
    )

    with pytest.raises(RuntimeError, match="simulated model crash"):
        await _collect(
            AgentRunner.for_agent_instance(target).run(
                RunAgentInput(state_id="context-retry", instruction="answer")
            )
        )
    resumed = await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(
                state_id="context-retry",
                instruction="answer",
                resume=True,
            )
        )
    )

    assert resumed[-1].kind is AgentYieldKind.FINAL
    assert provider.calls == [1, 1]
    context_evidence = [
        item.kind
        for item in evidence.list_by_state("context-retry")
        if item.kind in (AgentEvidenceKind.CONTEXT, AgentEvidenceKind.CONTEXT_MANIFEST)
    ]
    assert context_evidence == [
        AgentEvidenceKind.CONTEXT,
        AgentEvidenceKind.CONTEXT_MANIFEST,
    ]


async def test_agent_runner_same_step_changed_context_appends_new_safe_evidence() -> (
    None
):
    """Changed model-bound content gets a new fingerprint and evidence set."""
    provider = RecordingContextProvider(
        (
            AgentContext(
                packs=(
                    ContextPack(
                        "retry-context",
                        "content-1",
                        "provider",
                        ContextPackRole.STATE,
                    ),
                )
            ),
            AgentContext(
                packs=(
                    ContextPack(
                        "retry-context",
                        "content-2",
                        "provider",
                        ContextPackRole.STATE,
                    ),
                )
            ),
        ),
        sequential=True,
    )
    model = CrashThenDoneModel()
    states = FakeStateRepository()
    evidence = FakeEvidenceRepository()
    target = ContextProbeAgent(
        model,
        provider,
        states,
        FakeSignalRepository(()),
        evidence,
    )

    with pytest.raises(RuntimeError, match="simulated model crash"):
        await _collect(
            AgentRunner.for_agent_instance(target).run(
                RunAgentInput(state_id="context-changed-retry", instruction="answer")
            )
        )
    resumed = await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(
                state_id="context-changed-retry",
                instruction="answer",
                resume=True,
            )
        )
    )

    assert resumed[-1].kind is AgentYieldKind.FINAL
    assert [request.context[0].content for request in model.requests] == [
        "content-1",
        "content-2",
    ]
    artifacts = [
        item
        for item in evidence.list_by_state("context-changed-retry")
        if item.kind in (AgentEvidenceKind.CONTEXT, AgentEvidenceKind.CONTEXT_MANIFEST)
    ]
    assert len(artifacts) == 4
    assert len({item.digest for item in artifacts}) == 2
    assert len({item.manifest_ref for item in artifacts}) == 2
    assert "content-1" not in repr(artifacts)
    assert "content-2" not in repr(artifacts)


async def test_agent_runner_context_evidence_is_privacy_safe_and_exact() -> None:
    """Durable context evidence exposes provenance only and real available kinds."""
    pack = ContextPack(
        "evidence-pack",
        "raw secret context",
        "source:private",
        ContextPackRole.EVIDENCE,
        freshness=ContextFreshness.CURRENT,
        relevance=0.8,
        sensitivity=ContextSensitivity.CONFIDENTIAL,
        token_budget=ContextTokenBudget(max_tokens=8, estimated_tokens=4),
        sensitive_fields=(SensitiveFieldDescriptor((), SecretField()),),
        metadata={"raw_metadata": "must-not-leak"},
    )
    manifest = ContextManifest(
        id="manifest-evidence",
        entries=(
            ContextManifestEntry(
                pack_id=pack.id,
                source=pack.source,
                role=pack.role,
                origin_ref="origin:safe",
            ),
        ),
    )
    digest = ContextDigest(
        id="digest-evidence",
        context_identity="run:evidence",
        source_manifest_ref=manifest.id,
        digest="sha256:safe",
        derived_from_pack_ids=(pack.id,),
        algorithm="sha256",
        summary="raw digest summary must not leak",
        metadata={"raw": "must-not-leak"},
    )
    provider = RecordingContextProvider((AgentContext(),))
    states = FakeStateRepository()
    evidence = FakeEvidenceRepository()
    model = ScriptedRoundModel(((ModelStreamEvent(kind=ModelStreamEventKind.DONE),),))
    target = ContextProbeAgent(
        model,
        provider,
        states,
        FakeSignalRepository(()),
        evidence,
    )

    await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(
                state_id="context-evidence",
                instruction="answer",
                context=AgentContext(
                    packs=(pack,),
                    manifest=manifest,
                    digest=digest,
                ),
            )
        )
    )

    artifacts = [
        item
        for item in evidence.list_by_state("context-evidence")
        if item.kind
        in (
            AgentEvidenceKind.CONTEXT,
            AgentEvidenceKind.CONTEXT_MANIFEST,
            AgentEvidenceKind.CONTEXT_DIGEST,
        )
    ]
    assert [item.kind for item in artifacts] == [
        AgentEvidenceKind.CONTEXT,
        AgentEvidenceKind.CONTEXT_MANIFEST,
        AgentEvidenceKind.CONTEXT_DIGEST,
    ]
    serialized = repr([(item.payload, item.summary) for item in artifacts])
    assert "raw secret context" not in serialized
    assert "raw digest summary" not in serialized
    assert "must-not-leak" not in serialized
    assert all(item.summary is None for item in artifacts)
    context_artifact, manifest_artifact, digest_artifact = artifacts
    assert context_artifact.digest == manifest_artifact.digest
    assert digest_artifact.digest == "sha256:safe"
    assert digest_artifact.payload["context_fingerprint"] == context_artifact.digest
    request = model.requests[0]
    assert request.context[0].content == "[SECRET]"
    assert request.context[0].metadata == {}
    assert request.context_manifest is not None
    assert request.context_manifest.metadata == {}
    assert request.context_digest is not None
    assert request.context_digest.summary is None
    assert request.context_digest.metadata == {}


@pytest.mark.parametrize("surface", ["run", "events"])
@pytest.mark.parametrize("failure", ["error", "runtime", "timeout"])
async def test_agent_runner_context_provider_failure_is_typed_on_both_surfaces(
    surface: str,
    failure: str,
) -> None:
    """Context provider errors and deadline expiry become one typed model terminal."""
    state_id = f"context-{failure}-{surface}"
    provider = RecordingContextProvider(
        (AgentContext(),),
        error=(
            AgentDefinitionError("provider failed")
            if failure == "error"
            else RuntimeError("provider runtime failure")
            if failure == "runtime"
            else None
        ),
        hang=failure == "timeout",
    )
    model = ScriptedRoundModel(((ModelStreamEvent(kind=ModelStreamEventKind.DONE),),))
    states = FakeStateRepository()
    agent_type = TimeoutContextProbeAgent if failure == "timeout" else ContextProbeAgent
    target = agent_type(
        model,
        provider,
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )
    runner = AgentRunner.for_agent_instance(target)
    command = RunAgentInput(state_id=state_id, instruction="answer")
    expected_code = (
        "agent_timeout" if failure == "timeout" else "agent_model_execution_failed"
    )

    if surface == "events":
        events = [event async for event in runner.run_events(command)]
        terminal = events[-1]
        assert isinstance(terminal, RunFinishedEvent)
        assert terminal.error is not None
        assert terminal.error["code"] == expected_code
    else:
        items = await _collect(runner.run(command))
        error = items[-1].payload
        assert isinstance(error, Error)
        assert error.code == expected_code
    assert states.get(state_id).status is AgentStatus.FAILED
    assert model.requests == []


async def test_agent_runner_context_provider_rejects_invalid_return_value() -> None:
    class InvalidContextProvider(IAgentContextProvider):
        @override
        async def provide(
            self,
            run_input: RunAgentInput,
            model_step: int,
        ) -> AgentContext:
            return cast(AgentContext, object())

    model = ScriptedRoundModel(((ModelStreamEvent(kind=ModelStreamEventKind.DONE),),))
    states = FakeStateRepository()
    target = ContextProbeAgent(
        model,
        InvalidContextProvider(),
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )
    items = await _collect(
        AgentRunner.for_agent_instance(target).run(
            RunAgentInput(state_id="invalid-provider-context", instruction="answer")
        )
    )
    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.code == "agent_model_execution_failed"
