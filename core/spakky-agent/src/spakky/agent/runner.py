"""Framework-owned agent execution loop (ADR-0013 §1).

The runner generalizes the manual model -> tool -> evidence -> terminate loop
that ADR-0009 left in developer ``execute()`` bodies. A developer declares an
``@Agent`` spec plus ``@agent_tool`` methods; the framework provides the loop.
The runner consumes the provider-neutral model stream (C2), dispatches tool
calls through the discovered catalog (C4), records boundary/evidence (C3 model
contracts), consumes durable signals, drives the unified HITL pause -> approval
request -> resume flow (ADR-0013 §5), and terminates with a typed final output
shaped by ``spec.output_type``.

The runner exposes two streams over the same orchestration. ``run()`` yields the
public ``AgentYield`` vocabulary that inbound adapters already consume. ``run_events()``
yields the protocol-neutral ``AgentEvent`` taxonomy (ADR-0013 §3) that AG-UI (#414)
and A2A (#415) adapters project losslessly: the runner emits message/reasoning
deltas, the tool-call ``start``/``args-delta``/``end``/``result`` lifecycle, and
run/step boundaries as distinct events carrying attribution (agent / run / parent /
conversation), rather than collapsing them into coarse ``AgentYield`` items that an
adapter would have to re-expand. The fine-grained model-stream channels (C2
``ModelStreamEventKind`` message/reasoning/tool-args deltas) project one-to-one onto
the neutral taxonomy; ``REASONING_DELTA`` is omitted when the model declares no
reasoning capability (graceful degrade, ADR-0013 §4).
"""

from asyncio import TimeoutError, get_running_loop, timeout_at
from collections.abc import AsyncGenerator, Awaitable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from hashlib import sha256
from inspect import iscoroutinefunction
from json import dumps

from pydantic import BaseModel

from spakky.agent.approval import (
    AgentApprovalDecisionOutcome,
    AgentApprovalPlan,
    AgentApprovalRequest,
    materialize_agent_approval_decision_state,
    parse_agent_approval_decision_signal,
    plan_agent_tool_approval,
)
from spakky.agent.cancellation import (
    begin_agent_cancellation,
    complete_agent_cancellation,
    run_agent_cancellation_cleanup,
)
from spakky.agent.compaction import validate_tool_call_groups
from spakky.agent.delegation import DelegationToolResult
from spakky.agent.dispatcher import AgentToolDispatcher
from spakky.agent.error import (
    AbstractSpakkyAgentError,
    AgentDefinitionError,
    AgentModelConfigurationError,
    AgentPersistenceConfigurationError,
    AgentToolDispatchError,
)
from spakky.agent.event import (
    AgentEvent,
    AgentEventAttribution,
    ArtifactEvent,
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
from spakky.agent.evidence import (
    AgentEvidence,
    AgentEvidenceCandidate,
    AgentEvidenceKind,
)
from spakky.agent.execution import Agent, RecoveryStrategy, StreamingExposureMode
from spakky.agent.hooks import AgentSignalHookDescriptor
from spakky.agent.inbound import RunAgentInput
from spakky.agent.interfaces.model import (
    IAgentModel,
    JsonSchemaConstraint,
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
    ModelToolChoice,
    ModelToolSpec,
    ModelUsage,
    SamplingOptions,
    ToolCallingSpec,
)
from spakky.agent.interfaces.repository import (
    IAgentEvidenceRepository,
    IAgentSignalRepository,
    IAgentStateRepository,
)
from spakky.agent.interfaces.task_store import ConversationTurn, ITaskStore
from spakky.agent.recovery import (
    AgentActionBoundaryCheckpoint,
    AgentActionKind,
    AgentResumeAction,
    plan_agent_resume,
)
from spakky.agent.signal import AgentSignal, AgentSignalKind, ApprovalDecision
from spakky.agent.state import (
    AgentState,
    AgentStateReason,
    AgentStateTransition,
    AgentStatus,
)
from spakky.agent.tooling import (
    AgentToolDescriptor,
    AgentToolRuntimeContext,
    Idempotency,
)
from spakky.agent.types import JsonObject, JsonValue
from spakky.agent.yield_ import (
    AgentYield,
    AgentYieldKind,
    Cancel,
    Error,
    Evidence,
    Final,
    Progress,
    Token,
    Tool,
)
from spakky.core.common.error import AbstractSpakkyFrameworkError

DEFAULT_SYSTEM_INSTRUCTION = "Use the declared tools to accomplish the objective."
"""Fallback system message when an agent spec declares no instructions."""

DEFAULT_SAMPLING = SamplingOptions(temperature=0.0, max_tokens=512)
"""Deterministic default sampling for the framework-owned model request."""

ESTIMATED_CHARACTERS_PER_TOKEN = 4
"""Provider-neutral characters-per-token ratio for the compaction trigger estimate.

The core cannot call a provider tokenizer (it stays protocol-neutral, ADR-0013
§2), so the compaction trigger estimates token count from transcript length using
the widely-used ~4-characters-per-token approximation. The estimate only decides
*whether* the declared chain runs; the strategies themselves bound the result, so
an approximate trigger is sufficient.
"""


def _estimate_token_count(history: tuple[ModelMessage, ...]) -> int:
    """Estimate the token cost of a history from its transcript length."""
    characters = sum(len(message.content) for message in history)
    return characters // ESTIMATED_CHARACTERS_PER_TOKEN


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    """Neutral terminal summary returned when a spec declares no output type."""

    state_id: str
    status: str
    tool_calls: tuple[str, ...]
    evidence_count: int


RUNNER_CHECKPOINT_METADATA_KEY = "runner_checkpoint"
"""Durable state metadata key holding an interrupted iterative loop."""

LIMIT_MAX_STEPS_CODE = "agent_max_steps_exceeded"
LIMIT_MAX_TOOL_CALLS_CODE = "agent_max_tool_calls_exceeded"
LIMIT_MAX_TOKENS_CODE = "agent_max_tokens_exceeded"
LIMIT_USAGE_UNAVAILABLE_CODE = "agent_usage_unavailable"
LIMIT_TIMEOUT_CODE = "agent_timeout"
MODEL_EXECUTION_ERROR_CODE = "agent_model_execution_failed"
TOOL_EXECUTION_ERROR_CODE = "agent_tool_execution_failed"
CHECKPOINT_ERROR_CODE = "agent_checkpoint_invalid"
APPROVAL_ERROR_CODE = "agent_approval_invalid"
SYNC_TOOL_TIMEOUT_ERROR_CODE = "agent_sync_tool_timeout_unenforceable"
SIGNAL_PROJECTION_ERROR_CODE = "agent_signal_projection_unsupported"


@dataclass(frozen=True, slots=True)
class _PreparedToolCall:
    """Fully validated and authority-planned tool call in one model batch."""

    call: ModelToolCall
    descriptor: AgentToolDescriptor
    approval: AgentApprovalPlan


@dataclass(slots=True)
class _ModelStepAccumulator:
    """Collect one terminal model response before any tool dispatch."""

    content: list[str] = field(default_factory=list)
    candidates: list[ModelToolCall] = field(default_factory=list)
    usage: ModelUsage | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)
    error: ModelError | None = None
    terminal_count: int = 0

    def consume(self, event: ModelStreamEvent) -> None:
        """Accumulate terminal content, candidates, usage, routing, and errors."""
        if event.kind is ModelStreamEventKind.TOKEN_DELTA:
            self.content.append(event.token_delta or "")
        elif event.kind is ModelStreamEventKind.MESSAGE_DELTA:
            self.content.append(event.message_delta or "")
        elif (
            event.kind is ModelStreamEventKind.TOOL_CALL_CANDIDATE
            and event.tool_call is not None
        ):
            self.candidates.append(event.tool_call)
        elif event.kind is ModelStreamEventKind.ERROR and event.error is not None:
            self.error = event.error
        elif event.kind is ModelStreamEventKind.DONE:
            self.terminal_count += 1
        if event.usage is not None:
            self.usage = event.usage
        self.metadata.update(event.metadata)


@dataclass(slots=True)
class _ExecutionContext:
    """Mutable counters, transcript, and pending batch for one runner invocation."""

    state_id: str
    history: list[ModelMessage]
    assistant_text: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    step_count: int = 0
    tool_call_count: int = 0
    total_tokens: int = 0
    seen_call_ids: set[str] = field(default_factory=set)
    approved_call_fingerprints: set[str] = field(default_factory=set)
    pending_calls: list[ModelToolCall] = field(default_factory=list)
    deadline: float | None = None
    route_metadata: dict[str, JsonValue] = field(default_factory=dict)
    restored_from_checkpoint: bool = False
    terminal_error: ModelError | None = None
    event_cancel_error: JsonObject | None = None

    @property
    def counters(self) -> JsonObject:
        return {
            "model_steps": self.step_count,
            "tool_calls": self.tool_call_count,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True, slots=True)
class _AuthorizationResult:
    """Authority evaluation outcome for an already validated pending batch."""

    approvals: tuple[AgentYield[object], ...] = ()
    prepared: tuple[_PreparedToolCall, ...] = ()
    error: ModelError | None = None
    paused: bool = False


@dataclass(frozen=True, slots=True)
class AgentRunner:
    """Framework-owned standard agent loop bound to one agent instance.

    Durable repositories are ``None`` for a stateless agent (one that declares
    no ``accepted_signals`` and no action-boundary recovery). In that mode the
    runner skips state/evidence/signal handling and runs model -> tool -> final.
    """

    agent: Agent
    # target: the @Agent instance owning the @agent_tool callables — no base type.
    target: object
    model: IAgentModel
    states: IAgentStateRepository | None = None
    signals: IAgentSignalRepository | None = None
    evidence: IAgentEvidenceRepository | None = None
    # task_store is None for a run that has no server-persisted conversation; the
    # caller then carries history inline via RunAgentInput.message_history or runs
    # single-turn (ADR-0013 §6).
    task_store: ITaskStore | None = None

    @classmethod
    def for_agent_instance(cls, instance: object) -> "AgentRunner":
        """Resolve runner ports from an agent instance's injected attributes.

        ADR-0009 stores constructor-injected ports as instance attributes, so the
        runner reads ``vars(instance)`` (the typed instance ``__dict__``, not the
        banned ``getattr``) and resolves each port by runtime type. Attribute
        names are developer-chosen, so resolution is type-driven, not name-driven.
        """
        agent = Agent.get(type(instance))
        attributes = tuple(vars(instance).values())
        model = cls._resolve_required(attributes, IAgentModel)
        if model is None:
            raise AgentModelConfigurationError(
                "Agent run requires an IAgentModel port but none was injected"
            )
        states = cls._resolve_optional(attributes, IAgentStateRepository)
        signals = cls._resolve_optional(attributes, IAgentSignalRepository)
        evidence = cls._resolve_optional(attributes, IAgentEvidenceRepository)
        task_store = cls._resolve_optional(attributes, ITaskStore)
        runner = cls(
            agent=agent,
            target=instance,
            model=model,
            states=states,
            signals=signals,
            evidence=evidence,
            task_store=task_store,
        )
        runner._require_durable_ports()
        return runner

    def with_model(self, model: IAgentModel) -> "AgentRunner":
        """Return a runner using a run-specific model adapter."""
        return replace(self, model=model)

    async def run(
        self,
        run_input: RunAgentInput,
    ) -> AsyncGenerator[AgentYield[object], None]:
        """Run one model-mediated agent loop, yielding the public stream."""
        if self.states is None:
            async for item in self._run_stateless(run_input):
                yield item
            return
        async for item in self._run_durable(run_input, self.states):
            yield item

    async def run_events(
        self,
        run_input: RunAgentInput,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Run the bounded iterative loop as protocol-neutral lifecycle events."""
        attribution = self._event_attribution(run_input)
        state = (
            self._ensure_active_state(run_input, self.states)
            if self.states is not None
            else None
        )
        try:
            context = await self._execution_context(run_input, state)
        except AbstractSpakkyFrameworkError as error:
            terminal = _framework_error(
                CHECKPOINT_ERROR_CODE,
                "Agent checkpoint could not be restored",
                error,
            )
            self._fail_execution(state, terminal)
            yield RunStartedEvent(attribution)
            yield RunFinishedEvent(
                attribution,
                error=_model_error_json(terminal),
            )
            return
        cursor = _MessageCursor(state_id=run_input.state_id)
        yield RunStartedEvent(attribution, metadata=context.counters)
        if (
            state is not None
            and run_input.resume
            and context.pending_calls
            and self._pending_resume_requires_hitl(state)
        ):
            yield _run_paused_event(
                self._states_required().get(state.id),
                attribution,
            )
            return
        while True:
            cancel = await self._poll_cancel(state)
            if cancel is not None:
                yield RunFinishedEvent(
                    attribution,
                    error=_cancel_error(cancel),
                    metadata=context.counters,
                )
                return
            if context.pending_calls:
                outcome = self._authorize_pending_batch(state, context)
                if outcome.error is not None:
                    self._fail_execution(state, outcome.error)
                    yield RunFinishedEvent(
                        attribution,
                        error=_model_error_json(outcome.error),
                        metadata={**context.counters, **context.route_metadata},
                    )
                    return
                if outcome.paused:
                    current = self._states_required().get(context.state_id)
                    yield _run_paused_event(current, attribution)
                    return
                try:
                    async for item in self._dispatch_pending_batch_as_events(
                        state,
                        context,
                        attribution,
                        cursor,
                        outcome.prepared,
                    ):
                        yield item
                except TimeoutError:
                    error = self._timeout_error(context)
                    self._fail_execution(state, error)
                    yield RunFinishedEvent(
                        attribution,
                        error=_model_error_json(error),
                        metadata=context.counters,
                    )
                    return
                if context.event_cancel_error is not None:
                    yield RunFinishedEvent(
                        attribution,
                        error=context.event_cancel_error,
                        metadata=context.counters,
                    )
                    return
                if context.terminal_error is not None:
                    self._fail_execution(state, context.terminal_error)
                    yield RunFinishedEvent(
                        attribution,
                        error=_model_error_json(context.terminal_error),
                        metadata={**context.counters, **context.route_metadata},
                    )
                    return
                if state is not None:
                    current = self._states_required().get(state.id)
                    if current.status is not AgentStatus.ACTIVE:
                        yield RunFinishedEvent(
                            attribution,
                            error=_state_error(current),
                            metadata=context.counters,
                        )
                        return
                continue
            limit_error = self._before_model_limit(context)
            if limit_error is not None:
                self._fail_execution(state, limit_error)
                yield RunFinishedEvent(
                    attribution,
                    error=_model_error_json(limit_error),
                    metadata=context.counters,
                )
                return
            context.step_count += 1
            cursor.begin_step(context.step_count)
            step_name = f"model-{context.step_count}"
            yield StepStartedEvent(
                attribution,
                step_name=step_name,
                metadata=context.counters,
            )
            accumulator = _ModelStepAccumulator()
            if state is not None:
                self._append_boundary(
                    state.id,
                    _before_model(self._model_action_id(context.step_count)),
                )
            try:
                async for event in self._model_events(
                    run_input,
                    context,
                ):
                    cancel = await self._poll_cancel(state)
                    if cancel is not None:
                        yield StepFinishedEvent(
                            attribution,
                            step_name=step_name,
                            metadata=context.counters,
                        )
                        yield RunFinishedEvent(
                            attribution,
                            error=_cancel_error(cancel),
                            metadata=context.counters,
                        )
                        return
                    accumulator.consume(event)
                    if state is not None:
                        async for signal_event in self._consume_inbound_signal_events(
                            state,
                            attribution,
                            context,
                        ):
                            yield signal_event
                        if context.terminal_error is not None:
                            self._fail_execution(state, context.terminal_error)
                            yield StepFinishedEvent(
                                attribution,
                                step_name=step_name,
                                metadata=context.counters,
                            )
                            yield RunFinishedEvent(
                                attribution,
                                error=_model_error_json(context.terminal_error),
                                metadata=context.counters,
                            )
                            return
                    async for item in self._project_model_event(
                        event,
                        attribution,
                        cursor,
                        run_input,
                    ):
                        yield item
                    if accumulator.error is not None:
                        break
            except TimeoutError:
                error = self._timeout_error(context)
                self._fail_execution(state, error)
                yield StepFinishedEvent(
                    attribution,
                    step_name=step_name,
                    metadata=context.counters,
                )
                yield RunFinishedEvent(
                    attribution,
                    error=_model_error_json(error),
                    metadata=context.counters,
                )
                return
            except AbstractSpakkyFrameworkError as framework_error:
                error = _framework_error(
                    MODEL_EXECUTION_ERROR_CODE,
                    "Agent model execution failed",
                    framework_error,
                    context,
                )
                self._fail_execution(state, error)
                metadata = {**context.counters, **context.route_metadata}
                yield StepFinishedEvent(
                    attribution,
                    step_name=step_name,
                    metadata=metadata,
                )
                yield RunFinishedEvent(
                    attribution,
                    error=_model_error_json(error),
                    metadata=metadata,
                )
                return
            if state is not None:
                self._append_boundary(
                    state.id,
                    _after_model(self._model_action_id(context.step_count)),
                )
            step_error = self._finish_model_step(
                run_input,
                state,
                context,
                accumulator,
            )
            step_metadata = self._step_metadata(context, accumulator)
            yield StepFinishedEvent(
                attribution,
                step_name=step_name,
                metadata=step_metadata,
            )
            if step_error is not None:
                self._fail_execution(state, step_error)
                yield RunFinishedEvent(
                    attribution,
                    error=_model_error_json(step_error),
                    metadata=step_metadata,
                )
                return
            if state is not None:
                current = self._states_required().get(state.id)
                if current.status is not AgentStatus.ACTIVE:
                    if current.status is AgentStatus.INTERRUPTED:
                        yield _run_paused_event(current, attribution)
                    else:
                        yield RunFinishedEvent(
                            attribution,
                            error=_state_error(current),
                            metadata=step_metadata,
                        )
                    return
            if context.pending_calls:
                continue
            if state is not None:
                self._complete_state(state.id, context)
            self._persist_turns(run_input, context.assistant_text)
            yield RunFinishedEvent(attribution, metadata=step_metadata)
            return

    async def _project_model_event(
        self,
        event: ModelStreamEvent,
        attribution: AgentEventAttribution,
        cursor: "_MessageCursor",
        run_input: RunAgentInput,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Project one model event without dispatching a candidate batch."""
        match event.kind:
            case ModelStreamEventKind.TOKEN_DELTA:
                yield MessageDeltaEvent(
                    attribution,
                    message_id=cursor.message_id,
                    delta=event.token_delta or "",
                    metadata=event.metadata,
                )
            case ModelStreamEventKind.MESSAGE_DELTA:
                yield MessageDeltaEvent(
                    attribution,
                    message_id=cursor.message_id,
                    delta=event.message_delta or "",
                    metadata=event.metadata,
                )
            case ModelStreamEventKind.REASONING_DELTA:
                if self._model_capability(run_input).supports_reasoning:
                    yield ReasoningDeltaEvent(
                        attribution,
                        reasoning_id=cursor.reasoning_id,
                        delta=event.reasoning_delta or "",
                        metadata=event.metadata,
                    )
            case ModelStreamEventKind.TOOL_CALL_START if event.tool_call is not None:
                yield ToolCallStartEvent(
                    attribution,
                    call_id=cursor.start_call_id(event.tool_call),
                    tool_name=event.tool_call.name,
                    parent_message_id=cursor.message_id,
                    metadata=event.metadata,
                )
            case ModelStreamEventKind.TOOL_CALL_ARGS_DELTA if (
                event.tool_call is not None
            ):
                yield ToolCallArgsDeltaEvent(
                    attribution,
                    call_id=cursor.active_call_id(event.tool_call),
                    args_delta=event.tool_call_args_delta or "",
                    metadata=event.metadata,
                )
            case ModelStreamEventKind.TOOL_CALL_END if event.tool_call is not None:
                yield ToolCallEndEvent(
                    attribution,
                    call_id=cursor.end_call_id(event.tool_call),
                    metadata=event.metadata,
                )
            case ModelStreamEventKind.TOOL_CALL_CANDIDATE if (
                event.tool_call is not None
            ):
                call_id, start_needed, end_needed = cursor.candidate_frame(
                    event.tool_call
                )
                metadata = {**event.metadata, **event.tool_call.metadata}
                if start_needed:
                    yield ToolCallStartEvent(
                        attribution,
                        call_id=call_id,
                        tool_name=event.tool_call.name,
                        parent_message_id=cursor.message_id,
                        metadata=metadata,
                    )
                if end_needed:
                    yield ToolCallEndEvent(
                        attribution,
                        call_id=call_id,
                        metadata=metadata,
                    )
            case _:
                return

    def _event_attribution(
        self,
        run_input: RunAgentInput,
    ) -> AgentEventAttribution:
        return AgentEventAttribution(
            agent_id=self._agent_type(),
            run_id=run_input.state_id,
            conversation_id=run_input.effective_conversation_id,
            parent_run_id=run_input.parent_run_id,
        )

    def _complete_state(
        self,
        state_id: str,
        context: _ExecutionContext,
    ) -> None:
        current = self._states_required().get(state_id)
        self._states_required().save(
            replace(
                current,
                status=AgentStatus.COMPLETED,
                transition=AgentStateTransition.COMPLETED,
                current_activity="run completed",
                metadata={
                    **current.metadata,
                    RUNNER_CHECKPOINT_METADATA_KEY: _context_metadata(context),
                },
            )
        )

    async def _run_stateless(
        self,
        run_input: RunAgentInput,
    ) -> AsyncGenerator[AgentYield[object], None]:
        context = await self._execution_context(run_input, None)
        async for item in self._run_iterative_yields(run_input, None, context):
            yield item

    async def _run_durable(
        self,
        run_input: RunAgentInput,
        states: IAgentStateRepository,
    ) -> AsyncGenerator[AgentYield[object], None]:
        state = self._ensure_active_state(run_input, states)
        try:
            context = await self._execution_context(run_input, state)
        except AbstractSpakkyFrameworkError as error:
            yield self._fail_on_model_error(
                state,
                _framework_error(
                    CHECKPOINT_ERROR_CODE,
                    "Agent checkpoint could not be restored",
                    error,
                ),
            )
            return
        if run_input.resume:
            if context.pending_calls:
                if self._pending_resume_requires_hitl(state):
                    yield _progress(
                        "resume action: require_hitl",
                        "resume",
                    )
                    return
                yield _progress(
                    "resume action: pending tool batch",
                    "resume",
                )
            else:
                yield self._emit_resume_plan(state)
                state = states.get(run_input.state_id)
        async for item in self._run_iterative_yields(run_input, state, context):
            yield item

    def _pending_resume_requires_hitl(self, state: AgentState) -> bool:
        plan = plan_agent_resume(
            state,
            self._evidence_required().list_by_state(state.id),
            self._signals_required().list_pending(state.id),
        )
        if (
            plan.action is AgentResumeAction.REQUIRE_HITL
            and plan.boundary is not None
            and plan.boundary.action_kind is AgentActionKind.TOOL_CALL
        ):
            self._states_required().save(plan.state)
            return True
        return False

    async def _run_iterative_yields(
        self,
        run_input: RunAgentInput,
        state: AgentState | None,
        context: _ExecutionContext,
    ) -> AsyncGenerator[AgentYield[object], None]:
        """Run the shared bounded model/batch loop for the public yield surface."""
        while True:
            cancel = await self._poll_cancel(state)
            if cancel is not None:
                yield cancel
                return
            if context.pending_calls:
                authorization = self._authorize_pending_batch(state, context)
                for approval in authorization.approvals:
                    yield approval
                if authorization.paused:
                    return
                if authorization.error is not None:
                    yield self._fail_on_model_error(state, authorization.error)
                    return
                try:
                    async for item in self._dispatch_pending_batch_as_yields(
                        run_input,
                        state,
                        context,
                        authorization.prepared,
                    ):
                        yield item
                except TimeoutError:
                    error = self._timeout_error(context)
                    yield self._fail_on_model_error(state, error)
                    return
                if context.terminal_error is not None:
                    yield self._fail_on_model_error(state, context.terminal_error)
                    return
                if state is not None:
                    current = self._states_required().get(state.id)
                    if current.status is not AgentStatus.ACTIVE:
                        if current.status is AgentStatus.CANCELLED:
                            return
                        yield _error_yield(_state_model_error(current))
                        return
                continue
            limit_error = self._before_model_limit(context)
            if limit_error is not None:
                yield self._fail_on_model_error(state, limit_error)
                return
            context.step_count += 1
            step_name = f"model-{context.step_count}"
            yield _progress("preparing model request", step_name)
            accumulator = _ModelStepAccumulator()
            if state is not None:
                self._append_boundary(
                    state.id,
                    _before_model(self._model_action_id(context.step_count)),
                )
            try:
                async for event in self._model_events(run_input, context):
                    cancel = await self._poll_cancel(state)
                    if cancel is not None:
                        yield cancel
                        return
                    if state is not None:
                        async for signal_item in self._consume_inbound_signals(state):
                            yield signal_item
                    accumulator.consume(event)
                    if event.kind in (
                        ModelStreamEventKind.TOKEN_DELTA,
                        ModelStreamEventKind.MESSAGE_DELTA,
                    ):
                        yield _token(
                            event.token_delta or event.message_delta or "",
                            event.metadata,
                        )
                    elif (
                        event.kind is ModelStreamEventKind.REASONING_DELTA
                        and self._model_capability(run_input).supports_reasoning
                    ):
                        yield _token(event.reasoning_delta or "", event.metadata)
                    if accumulator.error is not None:
                        break
            except TimeoutError:
                yield self._fail_on_model_error(state, self._timeout_error(context))
                return
            except AbstractSpakkyFrameworkError as framework_error:
                yield self._fail_on_model_error(
                    state,
                    _framework_error(
                        MODEL_EXECUTION_ERROR_CODE,
                        "Agent model execution failed",
                        framework_error,
                        context,
                    ),
                )
                return
            if state is not None:
                self._append_boundary(
                    state.id,
                    _after_model(self._model_action_id(context.step_count)),
                )
            step_error = self._finish_model_step(
                run_input,
                state,
                context,
                accumulator,
            )
            if step_error is not None:
                yield self._fail_on_model_error(state, step_error)
                return
            if state is not None:
                current = self._states_required().get(state.id)
                if current.status is not AgentStatus.ACTIVE:
                    if current.status is not AgentStatus.INTERRUPTED:
                        yield _error_yield(_state_model_error(current))
                    return
            if context.pending_calls:
                continue
            if state is not None:
                self._complete_state(state.id, context)
            self._persist_turns(run_input, context.assistant_text)
            yield self._final_yield(
                run_input.state_id,
                context.tool_calls,
                evidence_count=(
                    self._evidence_count(run_input.state_id) if state is not None else 0
                ),
            )
            return

    async def _execution_context(
        self,
        run_input: RunAgentInput,
        state: AgentState | None,
    ) -> _ExecutionContext:
        """Create or restore the iterative transcript and enforced counters."""
        timeout_seconds = self.agent.spec.limits.timeout_seconds
        deadline = (
            get_running_loop().time() + timeout_seconds
            if timeout_seconds is not None
            else None
        )
        if state is not None and run_input.resume:
            checkpoint = state.metadata.get(RUNNER_CHECKPOINT_METADATA_KEY)
            if checkpoint is not None:
                if not isinstance(checkpoint, Mapping):
                    raise AgentDefinitionError("Agent runner checkpoint is invalid")
                context = self._context_from_checkpoint(run_input.state_id, checkpoint)
                context.deadline = deadline
                context.restored_from_checkpoint = True
                return context
        history = list(self._resolve_history(run_input))
        history.append(ModelMessage(ModelMessageRole.USER, run_input.instruction))
        return _ExecutionContext(
            state_id=run_input.state_id,
            history=history,
            deadline=deadline,
        )

    async def _model_events(
        self,
        run_input: RunAgentInput,
        context: _ExecutionContext,
    ) -> AsyncGenerator[ModelStreamEvent, None]:
        """Yield one model step from streaming or guarded complete execution."""
        if context.step_count == 1 and context.history:
            current_instruction = context.history[-1]
            compacted = await self._compact_history(
                tuple(context.history[:-1]),
                run_input.model_selection,
            )
            context.history = [*compacted, current_instruction]
        else:
            context.history = list(
                await self._compact_history(
                    tuple(context.history),
                    run_input.model_selection,
                )
            )
        request = self._model_request(run_input, tuple(context.history))
        if (
            self.agent.spec.streaming_exposure_mode
            is StreamingExposureMode.NO_STREAM_UNTIL_FINAL_GUARDED
        ):
            response = await self._await_with_deadline(
                self.model.complete(request),
                context.deadline,
            )
            async for event in self._response_events(response, context):
                yield event
            return
        iterator = self.model.stream(request).__aiter__()
        while True:
            try:
                event = await self._await_with_deadline(
                    anext(iterator),
                    context.deadline,
                )
            except StopAsyncIteration:
                return
            yield event

    async def _response_events(
        self,
        response: ModelResponse,
        context: _ExecutionContext,
    ) -> AsyncGenerator[ModelStreamEvent, None]:
        """Normalize complete responses into the same terminal step channels."""
        if response.content:
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.MESSAGE_DELTA,
                message_delta=response.content,
                metadata=response.metadata,
            )
        normalized_calls = self._normalize_candidate_ids(
            tuple(response.tool_calls),
            context,
            reserve=False,
        )
        for call in normalized_calls:
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.TOOL_CALL_START,
                tool_call=call,
                metadata=call.metadata,
            )
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.TOOL_CALL_END,
                tool_call=call,
                metadata=call.metadata,
            )
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
                tool_call=call,
                metadata=call.metadata,
            )
        if response.structured_output is not None:
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
                structured_output=response.structured_output,
                metadata=response.metadata,
            )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.DONE,
            usage=response.usage,
            metadata=response.metadata,
        )

    async def _await_with_deadline[ResultT](
        self,
        awaitable: Awaitable[ResultT],
        deadline: float | None,
    ) -> ResultT:
        """Await one model/tool operation inside the run wall-clock deadline."""
        if deadline is None:
            return await awaitable
        async with timeout_at(deadline):
            return await awaitable

    def _finish_model_step(
        self,
        run_input: RunAgentInput,
        state: AgentState | None,
        context: _ExecutionContext,
        accumulator: _ModelStepAccumulator,
    ) -> ModelError | None:
        """Apply usage limits, validate a whole candidate batch, and checkpoint."""
        context.route_metadata.update(_routing_metadata(accumulator.metadata))
        if accumulator.error is not None:
            return replace(
                accumulator.error,
                metadata={
                    **accumulator.error.metadata,
                    **self._step_metadata(context, accumulator),
                },
            )
        if accumulator.terminal_count != 1:
            return ModelError(
                code="agent_model_terminal_invalid",
                message="Agent model step requires exactly one terminal DONE event",
                metadata=self._step_metadata(context, accumulator),
            )
        usage_error = self._record_usage(context, accumulator.usage)
        if usage_error is not None:
            usage_error = replace(
                usage_error,
                metadata={
                    **usage_error.metadata,
                    **self._step_metadata(context, accumulator),
                },
            )
            if state is not None:
                self._append_model_evidence(
                    state.id,
                    context,
                    accumulator,
                    error=usage_error,
                )
            return usage_error
        content = "".join(accumulator.content)
        context.assistant_text.extend(accumulator.content)
        if accumulator.candidates:
            try:
                prepared = self._prepare_batch(
                    tuple(accumulator.candidates),
                    context,
                    reserve=True,
                )
            except AbstractSpakkyAgentError as error:
                return ModelError(
                    code="agent_tool_batch_invalid",
                    message=error.message,
                    metadata={**context.counters, **context.route_metadata},
                )
            tool_limit_error = self._before_tool_batch_limit(context, len(prepared))
            if tool_limit_error is not None:
                return tool_limit_error
            context.pending_calls = [item.call for item in prepared]
            context.history.append(
                _assistant_tool_message(
                    content,
                    context.pending_calls,
                    context.route_metadata,
                )
            )
            self._save_context(state, context)
        if state is not None:
            self._append_model_evidence(state.id, context, accumulator)
        _ = run_input
        return None

    def _prepare_batch(
        self,
        calls: tuple[ModelToolCall, ...],
        context: _ExecutionContext,
        *,
        reserve: bool,
    ) -> tuple[_PreparedToolCall, ...]:
        """Prevalidate every descriptor, binding, correlation, and approval plan."""
        normalized = self._normalize_candidate_ids(calls, context, reserve=reserve)
        dispatcher = AgentToolDispatcher(
            target=self.target, catalog=self.agent.tool_catalog
        )
        prepared: list[_PreparedToolCall] = []
        for call in normalized:
            descriptor = dispatcher.descriptor_for(call)
            descriptor.bind_invocation(call.arguments)
            approval_context = descriptor.approval_context(call.arguments)
            approval = plan_agent_tool_approval(
                descriptor=descriptor,
                approval_id=self._approval_id(context.state_id, call),
                agent_state_id=context.state_id,
                agent_type=self._agent_type(),
                prompt=approval_context.prompt,
                action_ref=approval_context.action_ref,
                call_id=call.call_id,
                metadata={
                    **approval_context.metadata,
                    "arguments_digest": _arguments_digest(call.arguments),
                },
            )
            prepared.append(_PreparedToolCall(call, descriptor, approval))
        return tuple(prepared)

    def _normalize_candidate_ids(
        self,
        calls: tuple[ModelToolCall, ...],
        context: _ExecutionContext,
        *,
        reserve: bool,
    ) -> tuple[ModelToolCall, ...]:
        """Bind missing ids to model-step/batch indexes and reject collisions."""
        batch_ids: set[str] = set()
        normalized: list[ModelToolCall] = []
        for index, call in enumerate(calls, start=1):
            call_id = call.call_id
            if call_id is None:
                call_id = f"{context.state_id}:model-{context.step_count}:call-{index}"
            if not call_id.strip() or call_id in batch_ids:
                raise AgentToolDispatchError("Agent tool call ids must be unique")
            if reserve and call_id in context.seen_call_ids:
                raise AgentToolDispatchError("Agent tool call id was already used")
            batch_ids.add(call_id)
            normalized.append(replace(call, call_id=call_id))
        if reserve:
            context.seen_call_ids.update(batch_ids)
        return tuple(normalized)

    def _authorize_pending_batch(
        self,
        state: AgentState | None,
        context: _ExecutionContext,
    ) -> _AuthorizationResult:
        """Clear every authority gate before the first tool in a batch dispatches."""
        try:
            prepared = list(
                self._prepare_batch(
                    tuple(context.pending_calls), context, reserve=False
                )
            )
        except AbstractSpakkyFrameworkError as error:
            code = (
                CHECKPOINT_ERROR_CODE
                if context.restored_from_checkpoint
                else APPROVAL_ERROR_CODE
            )
            return _AuthorizationResult(
                error=_framework_error(
                    code,
                    "Agent pending tool batch is invalid",
                    error,
                    context,
                )
            )
        sync_timeout_error = self._sync_tool_timeout_error(prepared, context)
        if sync_timeout_error is not None:
            return _AuthorizationResult(error=sync_timeout_error)
        approvals: list[AgentYield[object]] = []
        for index, item in enumerate(prepared):
            if not item.approval.requires_approval:
                continue
            approval_fingerprint = self._approval_id(context.state_id, item.call)
            if approval_fingerprint in context.approved_call_fingerprints:
                continue
            if state is None:
                return _AuthorizationResult(
                    error=_approval_unavailable_error(context),
                )
            request = item.approval.request
            yield_item = item.approval.yield_item
            planned_state = item.approval.state
            if request is None or yield_item is None or planned_state is None:
                return _AuthorizationResult(
                    error=ModelError(
                        code="agent_approval_invalid",
                        message="Agent approval plan is invalid",
                        metadata=context.counters,
                    )
                )
            self._append_boundary(
                state.id,
                _before_approval(item.call, item.descriptor),
            )
            approval_item = AgentYield[object](
                kind=yield_item.kind,
                payload=yield_item.payload,
            )
            approvals.append(approval_item)
            try:
                outcome = self._consume_approval_outcome(state.id, request)
            except AbstractSpakkyFrameworkError as error:
                return _AuthorizationResult(
                    approvals=tuple(approvals),
                    error=_framework_error(
                        APPROVAL_ERROR_CODE,
                        "Agent approval decision is invalid",
                        error,
                        context,
                    ),
                )
            if outcome is None:
                self._save_approval_pause(state.id, planned_state, context)
                return _AuthorizationResult(
                    approvals=tuple(approvals),
                    paused=True,
                )
            if outcome.decision not in (
                ApprovalDecision.APPROVE,
                ApprovalDecision.MODIFY,
            ):
                self._save_context(self._states_required().get(state.id), context)
                return _AuthorizationResult(
                    approvals=tuple(approvals),
                    paused=outcome.decision is ApprovalDecision.DEFER,
                    error=(
                        None
                        if outcome.decision is ApprovalDecision.DEFER
                        else _state_model_error(self._states_required().get(state.id))
                    ),
                )
            approved_call = item.call
            if outcome.decision is ApprovalDecision.MODIFY:
                try:
                    approved_call = replace(
                        item.call,
                        arguments=outcome.modified_payload,
                    )
                    item.descriptor.bind_invocation(approved_call.arguments)
                    updated_history = _history_with_approved_call(
                        context.history,
                        approved_call,
                    )
                except AbstractSpakkyFrameworkError as error:
                    return _AuthorizationResult(
                        approvals=tuple(approvals),
                        error=_framework_error(
                            APPROVAL_ERROR_CODE,
                            "Agent modified approval payload is invalid",
                            error,
                            context,
                        ),
                    )
                context.pending_calls[index] = approved_call
                context.history = list(updated_history)
                prepared[index] = _PreparedToolCall(
                    approved_call,
                    item.descriptor,
                    item.approval,
                )
            context.approved_call_fingerprints.add(
                self._approval_id(context.state_id, approved_call)
            )
            self._append_boundary(
                state.id,
                _after_approval(approved_call, item.descriptor),
            )
            self._save_context(self._states_required().get(state.id), context)
        return _AuthorizationResult(
            approvals=tuple(approvals),
            prepared=tuple(prepared),
        )

    def _sync_tool_timeout_error(
        self,
        prepared: Sequence[_PreparedToolCall],
        context: _ExecutionContext,
    ) -> ModelError | None:
        for item in prepared:
            has_deadline = (
                context.deadline is not None
                or item.descriptor.metadata.timeout.seconds is not None
            )
            if has_deadline and not iscoroutinefunction(item.descriptor.callable):
                return _limit_error(
                    SYNC_TOOL_TIMEOUT_ERROR_CODE,
                    "Agent cannot enforce a deadline on an in-process sync tool",
                    context,
                )
        return None

    async def _dispatch_pending_batch_as_yields(
        self,
        run_input: RunAgentInput,
        state: AgentState | None,
        context: _ExecutionContext,
        prepared: Sequence[_PreparedToolCall],
    ) -> AsyncGenerator[AgentYield[object], None]:
        """Dispatch an authorized batch in order and extend continuation history."""
        for item in prepared:
            cancel = await self._poll_cancel(state)
            if cancel is not None:
                yield cancel
                return
            yield _progress(
                f"dispatching tool: {item.call.name}",
                f"tool-{context.tool_call_count + 1}",
            )
            if state is not None:
                self._append_boundary(
                    state.id, _before_tool(item.descriptor, item.call)
                )
            try:
                result_object = await self._await_with_deadline(
                    self._dispatch(item.call, self._event_attribution(run_input)),
                    self._tool_deadline(context, item.descriptor),
                )
            except AbstractSpakkyFrameworkError as error:
                context.terminal_error = _framework_error(
                    TOOL_EXECUTION_ERROR_CODE,
                    "Agent tool execution failed",
                    error,
                    context,
                )
                return
            cancel = await self._poll_cancel(state)
            if cancel is not None:
                yield cancel
                return
            if state is not None:
                async for signal_item in self._consume_inbound_signals(state):
                    yield signal_item
            try:
                result, evidence = self._commit_tool_result(
                    state,
                    context,
                    item,
                    result_object,
                )
            except AbstractSpakkyFrameworkError as error:
                context.terminal_error = _framework_error(
                    TOOL_EXECUTION_ERROR_CODE,
                    "Agent tool result is invalid",
                    error,
                    context,
                )
                return
            if evidence is not None:
                yield _evidence_yield(evidence)
            yield _tool_yield(item.descriptor, item.call, result)

    async def _dispatch_pending_batch_as_events(
        self,
        state: AgentState | None,
        context: _ExecutionContext,
        attribution: AgentEventAttribution,
        cursor: "_MessageCursor",
        prepared: Sequence[_PreparedToolCall],
    ) -> AsyncGenerator[AgentEvent, None]:
        """Dispatch an authorized batch with actual tool action step boundaries."""
        for item in prepared:
            step_name = f"tool-{context.tool_call_count + 1}"
            yield StepStartedEvent(attribution, step_name, metadata=context.counters)
            cancel = await self._poll_cancel(state)
            if cancel is not None:
                context.event_cancel_error = _cancel_error(cancel)
                yield StepFinishedEvent(
                    attribution,
                    step_name,
                    metadata=context.counters,
                )
                return
            if state is not None:
                self._append_boundary(
                    state.id, _before_tool(item.descriptor, item.call)
                )
            try:
                result_object = await self._await_with_deadline(
                    self._dispatch(item.call, attribution),
                    self._tool_deadline(context, item.descriptor),
                )
            except AbstractSpakkyFrameworkError as error:
                context.terminal_error = _framework_error(
                    TOOL_EXECUTION_ERROR_CODE,
                    "Agent tool execution failed",
                    error,
                    context,
                )
                yield StepFinishedEvent(
                    attribution,
                    step_name,
                    metadata={**context.counters, **context.route_metadata},
                )
                return
            cancel = await self._poll_cancel(state)
            if cancel is not None:
                context.event_cancel_error = _cancel_error(cancel)
                yield StepFinishedEvent(
                    attribution,
                    step_name,
                    metadata=context.counters,
                )
                return
            if state is not None:
                async for signal_event in self._consume_inbound_signal_events(
                    state,
                    attribution,
                    context,
                ):
                    yield signal_event
                if context.terminal_error is not None:
                    yield StepFinishedEvent(
                        attribution,
                        step_name,
                        metadata=context.counters,
                    )
                    return
            if isinstance(result_object, DelegationToolResult):
                for child_event in result_object.events:
                    yield child_event
            try:
                result, _ = self._commit_tool_result(
                    state,
                    context,
                    item,
                    result_object,
                )
            except AbstractSpakkyFrameworkError as error:
                context.terminal_error = _framework_error(
                    TOOL_EXECUTION_ERROR_CODE,
                    "Agent tool result is invalid",
                    error,
                    context,
                )
                yield StepFinishedEvent(
                    attribution,
                    step_name,
                    metadata={**context.counters, **context.route_metadata},
                )
                return
            metadata = {**context.counters, **context.route_metadata}
            yield ToolCallResultEvent(
                attribution,
                call_id=_call_id(item.call),
                tool_name=item.call.name,
                message_id=cursor.message_id,
                result=result,
                metadata=metadata,
            )
            yield StepFinishedEvent(attribution, step_name, metadata=metadata)

    def _commit_tool_result(
        self,
        state: AgentState | None,
        context: _ExecutionContext,
        item: _PreparedToolCall,
        result_object: object,
    ) -> tuple[JsonValue, AgentEvidence | None]:
        """Commit one completed tool result and its continuation/checkpoint state."""
        result = _tool_result_json(result_object)
        evidence: AgentEvidence | None = None
        if state is not None:
            evidence = self._append_tool_evidence(state.id, item.descriptor, result)
        context.tool_call_count += 1
        context.tool_calls.append(item.call.name)
        context.history.append(_tool_result_message(item.call, result))
        context.pending_calls = [
            call
            for call in context.pending_calls
            if _call_id(call) != _call_id(item.call)
        ]
        self._save_context(state, context)
        if state is not None:
            self._append_boundary(state.id, _after_tool(item.descriptor, item.call))
        return result, evidence

    def _before_model_limit(self, context: _ExecutionContext) -> ModelError | None:
        limits = self.agent.spec.limits
        if context.step_count >= limits.max_steps:
            return _limit_error(
                LIMIT_MAX_STEPS_CODE,
                "Agent model-step limit exceeded",
                context,
            )
        return None

    def _before_tool_batch_limit(
        self,
        context: _ExecutionContext,
        batch_size: int,
    ) -> ModelError | None:
        if context.tool_call_count + batch_size > self.agent.spec.limits.max_tool_calls:
            return _limit_error(
                LIMIT_MAX_TOOL_CALLS_CODE,
                "Agent tool-call limit exceeded",
                context,
            )
        return None

    def _record_usage(
        self,
        context: _ExecutionContext,
        usage: ModelUsage | None,
    ) -> ModelError | None:
        max_tokens = self.agent.spec.limits.max_tokens
        total_tokens = usage.total_tokens if usage is not None else None
        if max_tokens is not None and total_tokens is None:
            return _limit_error(
                LIMIT_USAGE_UNAVAILABLE_CODE,
                "Agent token limit requires provider total-token usage",
                context,
            )
        if total_tokens is not None:
            context.total_tokens += total_tokens
        if max_tokens is not None and context.total_tokens > max_tokens:
            return _limit_error(
                LIMIT_MAX_TOKENS_CODE,
                "Agent token limit exceeded",
                context,
            )
        return None

    def _timeout_error(self, context: _ExecutionContext) -> ModelError:
        return _limit_error(
            LIMIT_TIMEOUT_CODE,
            "Agent execution timed out",
            context,
        )

    def _tool_deadline(
        self,
        context: _ExecutionContext,
        descriptor: AgentToolDescriptor,
    ) -> float | None:
        tool_timeout = descriptor.metadata.timeout.seconds
        tool_deadline = (
            get_running_loop().time() + tool_timeout
            if tool_timeout is not None
            else None
        )
        deadlines = tuple(
            deadline
            for deadline in (context.deadline, tool_deadline)
            if deadline is not None
        )
        return min(deadlines, default=None)

    def _step_metadata(
        self,
        context: _ExecutionContext,
        accumulator: _ModelStepAccumulator,
    ) -> JsonObject:
        usage: JsonObject = {}
        if accumulator.usage is not None:
            usage = {
                "input_tokens": accumulator.usage.input_tokens,
                "output_tokens": accumulator.usage.output_tokens,
                "total_tokens": accumulator.usage.total_tokens,
            }
        return {
            **context.counters,
            **context.route_metadata,
            "usage": usage,
        }

    async def _poll_cancel(
        self,
        state: AgentState | None,
    ) -> AgentYield[object] | None:
        if state is None:
            return None
        return await self._consume_cancel(self._states_required().get(state.id))

    def _save_approval_pause(
        self,
        state_id: str,
        planned_state: AgentState,
        context: _ExecutionContext,
    ) -> None:
        """Merge approval lifecycle into the current state without losing checkpoint."""
        current = self._states_required().get(state_id)
        paused = replace(
            current,
            status=planned_state.status,
            transition=planned_state.transition,
            reason=planned_state.reason,
            current_activity=planned_state.current_activity,
            metadata={**current.metadata, **planned_state.metadata},
        )
        self._states_required().save(paused)
        self._save_context(paused, context)

    def _consume_approval_outcome(
        self,
        state_id: str,
        request: AgentApprovalRequest,
    ) -> AgentApprovalDecisionOutcome | None:
        for signal in self._signals_required().list_pending(state_id):
            if signal.kind is not AgentSignalKind.APPROVAL_DECISION:
                continue
            if _optional_signal_text(signal, "request_id") != request.id:
                continue
            outcome = parse_agent_approval_decision_signal(signal, request=request)
            self._signals_required().mark_consumed(signal.id)
            current = self._states_required().get(state_id)
            self._states_required().save(
                materialize_agent_approval_decision_state(current, outcome)
            )
            self._append_candidate(
                state_id,
                AgentEvidenceCandidate(
                    kind=AgentEvidenceKind.APPROVAL,
                    payload={
                        "signal_id": signal.id,
                        "request_id": outcome.request_id,
                        "decision": outcome.decision.value,
                        "modified_payload": outcome.modified_payload,
                    },
                    summary="approval decision consumed",
                ),
            )
            return outcome
        return None

    def _save_context(
        self,
        state: AgentState | None,
        context: _ExecutionContext,
    ) -> None:
        if state is None:
            return
        current = self._states_required().get(state.id)
        self._states_required().save(
            replace(
                current,
                metadata={
                    **current.metadata,
                    RUNNER_CHECKPOINT_METADATA_KEY: _context_metadata(context),
                },
            )
        )

    def _context_from_checkpoint(
        self,
        state_id: str,
        checkpoint: Mapping[str, JsonValue],
    ) -> _ExecutionContext:
        return _ExecutionContext(
            state_id=state_id,
            history=[
                _message_from_metadata(value)
                for value in _mapping_sequence(checkpoint, "history")
            ],
            assistant_text=list(_string_sequence(checkpoint, "assistant_text")),
            tool_calls=list(_string_sequence(checkpoint, "tool_calls")),
            step_count=_integer_metadata(checkpoint, "step_count"),
            tool_call_count=_integer_metadata(checkpoint, "tool_call_count"),
            total_tokens=_integer_metadata(checkpoint, "total_tokens"),
            seen_call_ids=set(_string_sequence(checkpoint, "seen_call_ids")),
            approved_call_fingerprints=set(
                _string_sequence(checkpoint, "approved_call_fingerprints")
            ),
            pending_calls=[
                _call_from_metadata(value)
                for value in _mapping_sequence(checkpoint, "pending_calls")
            ],
            route_metadata=dict(_mapping_metadata(checkpoint, "route_metadata")),
        )

    def _append_model_evidence(
        self,
        state_id: str,
        context: _ExecutionContext,
        accumulator: _ModelStepAccumulator,
        *,
        error: ModelError | None = None,
    ) -> AgentEvidence:
        model = context.route_metadata.get("model")
        model_name = model if isinstance(model, str) and model.strip() else "unknown"
        return self._append_candidate(
            state_id,
            AgentEvidenceCandidate.model_decision(
                model=model_name,
                decision={
                    "step": context.step_count,
                    "tool_calls": len(accumulator.candidates),
                    "usage": self._step_metadata(context, accumulator).get("usage"),
                    "routing": context.route_metadata,
                    "limits": context.counters,
                    "error": None if error is None else _model_error_json(error),
                },
                summary=f"model-{context.step_count} completed",
            ),
        )

    def _fail_execution(
        self,
        state: AgentState | None,
        error: ModelError,
    ) -> None:
        if state is None:
            return
        self._fail_on_model_error(state, error)

    async def _dispatch(
        self,
        call: ModelToolCall,
        attribution: AgentEventAttribution,
    ) -> object:
        dispatcher = AgentToolDispatcher(
            target=self.target,
            catalog=self.agent.tool_catalog,
            runtime_context=AgentToolRuntimeContext(
                state_id=attribution.run_id,
                conversation_id=attribution.conversation_id,
                call_id=_call_id(call),
                tool_name=call.name,
            ),
        )
        return await dispatcher.dispatch(call)

    def _fail_on_model_error(
        self,
        state: AgentState | None,
        error: ModelError,
    ) -> AgentYield[object]:
        if state is not None:
            current = self._states_required().get(state.id)
            timed_out = error.code == LIMIT_TIMEOUT_CODE
            self._states_required().save(
                replace(
                    current,
                    status=AgentStatus.FAILED,
                    transition=(
                        AgentStateTransition.TIMED_OUT
                        if timed_out
                        else AgentStateTransition.FAILED
                    ),
                    reason=(
                        AgentStateReason.TIMEOUT
                        if timed_out
                        else AgentStateReason.EXECUTION_FAILED
                    ),
                    current_activity=(
                        "agent execution timed out"
                        if timed_out
                        else "agent execution failed"
                    ),
                    metadata={
                        **current.metadata,
                        "model_error_code": error.code,
                        "model_error_metadata": error.metadata,
                    },
                )
            )
        return AgentYield(
            kind=AgentYieldKind.ERROR,
            payload=Error(
                code=error.code,
                message=error.message,
                retryable=error.retryable,
                metadata=error.metadata,
            ),
        )

    def _ensure_active_state(
        self,
        run_input: RunAgentInput,
        states: IAgentStateRepository,
    ) -> AgentState:
        existing = states.get_or_none(run_input.state_id)
        if existing is not None:
            return states.save(
                replace(
                    existing,
                    status=AgentStatus.ACTIVE,
                    transition=AgentStateTransition.RUNNING,
                    current_activity=run_input.instruction,
                )
            )
        return states.save(
            AgentState(
                id=run_input.state_id,
                agent_type=self._agent_type(),
                status=AgentStatus.ACTIVE,
                transition=AgentStateTransition.RUNNING,
                current_activity=run_input.instruction,
                input_ref=run_input.instruction,
            )
        )

    def _emit_resume_plan(self, state: AgentState) -> AgentYield[object]:
        plan = plan_agent_resume(
            state,
            self._evidence_required().list_by_state(state.id),
            self._signals_required().list_pending(state.id),
        )
        self._states_required().save(plan.state)
        return AgentYield(
            kind=AgentYieldKind.PROGRESS,
            payload=Progress(
                f"resume action: {plan.action.value}",
                current_step="resume",
                metadata={
                    "requires_human_input": plan.requires_human_input,
                    "can_resume_automatically": plan.can_resume_automatically,
                },
            ),
        )

    def _model_request(
        self,
        run_input: RunAgentInput,
        history: tuple[ModelMessage, ...],
    ) -> ModelRequest:
        tools = tuple(
            ModelToolSpec(
                name=descriptor.schema.name,
                description=descriptor.description,
                parameters=JsonSchemaConstraint(schema=descriptor.schema.input_schema),
                metadata={"tool_identity": descriptor.identity.key},
            )
            for descriptor in self.agent.tool_catalog.descriptors
        )
        tool_calling = (
            ToolCallingSpec(tools=tools, choice=ModelToolChoice.AUTO) if tools else None
        )
        return ModelRequest(
            messages=(
                ModelMessage(
                    ModelMessageRole.SYSTEM,
                    self.agent.spec.instructions or DEFAULT_SYSTEM_INSTRUCTION,
                ),
                *history,
            ),
            tool_calling=tool_calling,
            sampling=DEFAULT_SAMPLING,
            model_selection=run_input.model_selection,
            metadata={"state_id": run_input.state_id, **run_input.metadata},
        )

    def _resolve_history(self, run_input: RunAgentInput) -> tuple[ModelMessage, ...]:
        """Resolve the prior-turn messages that seed this run's model request.

        The two ADR-0013 §6 multi-turn paths are mutually exclusive per run:
        client-injected ``message_history`` wins when present (the stateless
        caller owns the transcript), otherwise a wired ``TaskStore`` supplies the
        server-persisted transcript keyed by ``effective_conversation_id``. With
        neither, the run is single-turn and seeds from the instruction alone.
        """
        if run_input.message_history:
            return run_input.message_history
        if self.task_store is None:
            return ()
        return tuple(
            turn.as_model_message()
            for turn in self.task_store.load_history(
                run_input.effective_conversation_id
            )
        )

    async def _compact_history(
        self,
        history: tuple[ModelMessage, ...],
        model_selection: ModelSelection | None,
    ) -> tuple[ModelMessage, ...]:
        """Apply the declared compaction chain when the token estimate trips it.

        Compaction runs only when an agent declares a policy and the running token
        estimate of the resolved history crosses ``trigger_token_threshold`` — a
        short conversation is sent verbatim. The estimate and the backend
        ``ModelCapability`` are passed to each strategy so a strategy can scale its
        effect, then each strategy's output is threaded into the next (chain order
        is compaction order).
        """
        history = validate_tool_call_groups(history)
        policy = self.agent.spec.compaction
        if policy is None:
            return history
        usage = ModelUsage(total_tokens=_estimate_token_count(history))
        if (usage.total_tokens or 0) < policy.trigger_token_threshold:
            return history
        capability = self.model.capability_for(model_selection)
        for strategy in policy.strategies:
            history = await strategy.compact(history, usage, capability)
            history = validate_tool_call_groups(history)
        return history

    def _model_capability(self, run_input: RunAgentInput) -> ModelCapability:
        """Return capability for this run's selected model."""
        return self.model.capability_for(run_input.model_selection)

    def _persist_turns(
        self,
        run_input: RunAgentInput,
        assistant_text: Sequence[str],
    ) -> None:
        """Append this run's user and assistant turns to the persisted session.

        Only a server-persisted session (a wired ``TaskStore``) accumulates the
        transcript. A client-injected-history run owns its own transcript (the
        stateless ADR-0013 §6 path) and is never written back, even when a store
        is also wired — the two multi-turn paths stay mutually exclusive per run.
        A run that produced no assistant text persists only the user turn, so the
        next turn still sees this instruction.
        """
        if self.task_store is None or run_input.message_history:
            return
        reply = "".join(assistant_text)
        turns = [ConversationTurn(ModelMessageRole.USER, run_input.instruction)]
        if reply.strip():
            turns.append(ConversationTurn(ModelMessageRole.ASSISTANT, reply))
        self.task_store.append_turns(run_input.effective_conversation_id, turns)

    def _final_yield(
        self,
        state_id: str,
        tool_calls: Sequence[str],
        *,
        evidence_count: int,
    ) -> AgentYield[object]:
        output_type = self.agent.spec.output_type
        result = AgentRunResult(
            state_id=state_id,
            status=AgentStatus.COMPLETED.value,
            tool_calls=tuple(tool_calls),
            evidence_count=evidence_count,
        )
        return AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(
                output=result,
                metadata={
                    "output_type": output_type.__name__
                    if output_type is not None
                    else None,
                },
            ),
        )

    async def _consume_cancel(self, state: AgentState) -> AgentYield[object] | None:
        for signal in self._signals_required().list_pending(state.id):
            if signal.kind is not AgentSignalKind.CANCEL:
                continue
            self._signals_required().mark_consumed(signal.id)
            cancelling = self._states_required().save(
                begin_agent_cancellation(state, signal)
            )
            report = await run_agent_cancellation_cleanup(
                state=cancelling,
                signal=signal,
                tasks=(),
            )
            self._append_candidate(
                state.id,
                report.to_evidence_candidate(summary="cancel cleanup completed"),
            )
            completed = self._states_required().save(
                complete_agent_cancellation(cancelling, report)
            )
            return AgentYield(
                kind=AgentYieldKind.CANCEL,
                payload=Cancel(
                    reason=(
                        _optional_signal_text(signal, "reason")
                        or (completed.reason.value if completed.reason else None)
                    ),
                    requested_by=_optional_signal_text(signal, "requested_by"),
                    metadata={
                        "state": completed.status.value,
                        "signal_id": signal.id,
                    },
                ),
            )
        return None

    async def _consume_inbound_signals(
        self,
        state: AgentState,
    ) -> AsyncGenerator[AgentYield[object], None]:
        """Dispatch pending non-terminal signals at safe model/tool boundaries.

        Cancel and approval decisions own dedicated phases, so this poll handles
        the remaining inbound kinds. A declarative ``@on_signal`` hook, when one
        is declared for the kind, owns the reaction and its yielded items flow
        into the public stream. A ``USER_MESSAGE`` with no declared hook falls
        back to the built-in progress item so the default loop still observes the
        message. Other kinds with no hook stay pending for a later boundary rather
        than being silently consumed without a handler.
        """
        for signal in self._signals_required().list_pending(state.id):
            if signal.kind in (
                AgentSignalKind.CANCEL,
                AgentSignalKind.APPROVAL_DECISION,
            ):
                continue
            hooks = self.agent.signal_hook_catalog.hooks_for(signal.kind)
            if hooks:
                async for item in self._dispatch_signal_hooks(state, signal, hooks):
                    yield item
                continue
            if signal.kind is AgentSignalKind.USER_MESSAGE:
                yield self._consume_default_user_message(state, signal)

    async def _consume_inbound_signal_events(
        self,
        state: AgentState,
        attribution: AgentEventAttribution,
        context: _ExecutionContext,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Project the same consumed signal yields onto the neutral event surface."""
        async for item in self._consume_inbound_signals(state):
            event = _signal_yield_event(item, attribution)
            if isinstance(event, ModelError):
                context.terminal_error = event
                return
            yield event

    async def _dispatch_signal_hooks(
        self,
        state: AgentState,
        signal: AgentSignal,
        hooks: Sequence[AgentSignalHookDescriptor],
    ) -> AsyncGenerator[AgentYield[object], None]:
        self._signals_required().mark_consumed(signal.id)
        self._append_candidate(
            state.id,
            AgentEvidenceCandidate(
                kind=AgentEvidenceKind.EVALUATION,
                payload={"signal_id": signal.id, "payload": signal.payload},
                summary=f"{signal.kind.value} signal hook handled",
            ),
        )
        for hook in hooks:
            async for item in hook.callable(self.target, signal):
                yield item

    def _consume_default_user_message(
        self,
        state: AgentState,
        signal: AgentSignal,
    ) -> AgentYield[object]:
        self._signals_required().mark_consumed(signal.id)
        self._append_candidate(
            state.id,
            AgentEvidenceCandidate(
                kind=AgentEvidenceKind.EVALUATION,
                payload={"signal_id": signal.id, "payload": signal.payload},
                summary="user signal consumed",
            ),
        )
        return AgentYield(
            kind=AgentYieldKind.PROGRESS,
            payload=Progress(
                "user message consumed",
                current_step="signal",
                metadata={"signal_id": signal.id},
            ),
        )

    def _append_tool_evidence(
        self,
        state_id: str,
        descriptor: AgentToolDescriptor,
        result: JsonValue,
    ) -> AgentEvidence:
        payload = result if isinstance(result, Mapping) else {"result": result}
        return self._append_candidate(
            state_id,
            AgentEvidenceCandidate.tool_result(
                tool_identity=descriptor.identity.key,
                tool_schema_name=descriptor.schema.name,
                result=payload,
                capture=descriptor.metadata.evidence,
                summary=f"{descriptor.schema.name} completed",
            ),
        )

    def _append_boundary(
        self,
        state_id: str,
        checkpoint: AgentActionBoundaryCheckpoint,
    ) -> AgentEvidence:
        return self._append_candidate(
            state_id,
            checkpoint.to_evidence_candidate(summary=checkpoint.action_id),
        )

    def _append_candidate(
        self,
        state_id: str,
        candidate: AgentEvidenceCandidate,
    ) -> AgentEvidence:
        index = self._evidence_count(state_id) + 1
        return self._evidence_required().append(
            candidate.to_evidence(
                evidence_id=f"{state_id}:evidence:{index}",
                agent_state_id=state_id,
            )
        )

    def _evidence_count(self, state_id: str) -> int:
        return len(self._evidence_required().list_by_state(state_id))

    def _agent_type(self) -> str:
        return self.agent.spec.name or type(self.target).__name__

    def _model_action_id(self, step: int) -> str:
        return f"model:{self._agent_type()}:{step}"

    def _approval_id(self, state_id: str, call: ModelToolCall) -> str:
        return (
            f"approval:{state_id}:{_call_id(call)}:{_arguments_digest(call.arguments)}"
        )

    def _require_durable_ports(self) -> None:
        if not self._is_durable():
            return
        missing = tuple(
            name
            for name, port in (
                ("IAgentStateRepository", self.states),
                ("IAgentSignalRepository", self.signals),
                ("IAgentEvidenceRepository", self.evidence),
            )
            if port is None
        )
        if missing:
            raise AgentPersistenceConfigurationError(
                "Agent run requires durable repositories but these are missing: "
                + ", ".join(missing)
            )

    def _is_durable(self) -> bool:
        spec = self.agent.spec
        return (
            spec.recovery is RecoveryStrategy.ACTION_BOUNDARY
            or len(spec.accepted_signals) > 0
        )

    def _states_required(self) -> IAgentStateRepository:
        if self.states is None:  # pragma: no cover - durable guard
            raise AgentPersistenceConfigurationError(
                "Agent run reached a durable path without a state repository"
            )
        return self.states

    def _signals_required(self) -> IAgentSignalRepository:
        if self.signals is None:  # pragma: no cover - durable guard
            raise AgentPersistenceConfigurationError(
                "Agent run reached a durable path without a signal repository"
            )
        return self.signals

    def _evidence_required(self) -> IAgentEvidenceRepository:
        if self.evidence is None:  # pragma: no cover - durable guard
            raise AgentPersistenceConfigurationError(
                "Agent run reached a durable path without an evidence repository"
            )
        return self.evidence

    @staticmethod
    def _resolve_required[PortT](
        attributes: Sequence[object],
        port_type: type[PortT],
    ) -> PortT | None:
        matches = tuple(
            attribute for attribute in attributes if isinstance(attribute, port_type)
        )
        if len(matches) > 1:
            raise AgentModelConfigurationError(
                f"Agent run found multiple {port_type.__name__} ports injected"
            )
        return matches[0] if matches else None

    @staticmethod
    def _resolve_optional[PortT](
        attributes: Sequence[object],
        port_type: type[PortT],
    ) -> PortT | None:
        return AgentRunner._resolve_required(attributes, port_type)


@dataclass(slots=True)
class _MessageCursor:
    """Synthesize stable message/reasoning ids for one run's event stream.

    The C2 model stream carries no message or reasoning ids — those channels are
    plain text deltas. The neutral taxonomy (and AG-UI ``messageId``/``reasoningId``)
    needs a stable id so an adapter groups deltas and attaches a tool result to the
    right message. Each iterative model step receives its own assistant and reasoning
    ids, while missing tool-call ids are correlated by step and candidate order.
    """

    state_id: str
    step: int = 1
    missing_call_index: int = 0
    active_missing_ids: dict[str, list[str]] = field(default_factory=dict)
    completed_missing_ids: dict[str, list[str]] = field(default_factory=dict)
    started_call_ids: set[str] = field(default_factory=set)
    ended_call_ids: set[str] = field(default_factory=set)

    def begin_step(self, step: int) -> None:
        self.step = step
        self.missing_call_index = 0
        self.active_missing_ids.clear()
        self.completed_missing_ids.clear()
        self.started_call_ids.clear()
        self.ended_call_ids.clear()

    def start_call_id(self, call: ModelToolCall) -> str:
        if call.call_id is not None:
            call_id = call.call_id
            self.started_call_ids.add(call_id)
            return call_id
        self.missing_call_index += 1
        call_id = f"{self.state_id}:model-{self.step}:call-{self.missing_call_index}"
        self.active_missing_ids.setdefault(call.name, []).append(call_id)
        self.started_call_ids.add(call_id)
        return call_id

    def active_call_id(self, call: ModelToolCall) -> str:
        if call.call_id is not None:
            return call.call_id
        active = self.active_missing_ids.get(call.name, [])
        return active[-1] if active else self.start_call_id(call)

    def end_call_id(self, call: ModelToolCall) -> str:
        call_id = self.active_call_id(call)
        self.ended_call_ids.add(call_id)
        if call.call_id is None:
            self.active_missing_ids[call.name].pop()
            self.completed_missing_ids.setdefault(call.name, []).append(call_id)
        return call_id

    def candidate_frame(self, call: ModelToolCall) -> tuple[str, bool, bool]:
        """Return candidate correlation and synthesize only missing frame sides."""
        generated = False
        if call.call_id is not None:
            call_id = call.call_id
        else:
            completed = self.completed_missing_ids.get(call.name, [])
            active = self.active_missing_ids.get(call.name, [])
            if completed:
                call_id = completed.pop(0)
            elif active:
                call_id = active[-1]
            else:
                call_id = self.start_call_id(call)
                generated = True
        start_needed = generated or call_id not in self.started_call_ids
        end_needed = call_id not in self.ended_call_ids
        self.started_call_ids.add(call_id)
        self.ended_call_ids.add(call_id)
        if call.call_id is None:
            active = self.active_missing_ids.get(call.name, [])
            if active and active[-1] == call_id:
                active.pop()
        return call_id, start_needed, end_needed

    @property
    def message_id(self) -> str:
        return f"{self.state_id}:model-{self.step}:message"

    @property
    def reasoning_id(self) -> str:
        return f"{self.state_id}:model-{self.step}:reasoning"


async def runner_backed_execute(
    self: object,
    run_input: RunAgentInput,
) -> AsyncGenerator[AgentYield[object], None]:
    """Framework-provided ``execute()`` bound onto a declaration-only @Agent.

    ``@Agent`` binds this as the agent's ``execute()`` when the developer
    declares only a spec plus ``@agent_tool`` methods (ADR-0013 §1). It builds a
    runner from the agent instance's injected ports and replays its stream.
    """
    runner = AgentRunner.for_agent_instance(self)
    async for item in runner.run(run_input):
        yield item


def _progress(message: str, step: str) -> AgentYield[object]:
    return AgentYield(
        kind=AgentYieldKind.PROGRESS,
        payload=Progress(message, current_step=step),
    )


def _token(
    text: str,
    metadata: JsonObject | None = None,
) -> AgentYield[object]:
    return AgentYield(
        kind=AgentYieldKind.TOKEN,
        payload=Token(text, metadata={} if metadata is None else metadata),
    )


def _tool_yield(
    descriptor: AgentToolDescriptor,
    call: ModelToolCall,
    result: JsonValue,
) -> AgentYield[object]:
    return AgentYield(
        kind=AgentYieldKind.TOOL,
        payload=Tool(
            name=call.name,
            call_id=call.call_id,
            arguments=call.arguments,
            result=result,
            metadata={"tool_identity": descriptor.identity.key},
        ),
    )


def _evidence_yield(evidence: AgentEvidence) -> AgentYield[object]:
    return AgentYield(kind=AgentYieldKind.EVIDENCE, payload=Evidence(evidence=evidence))


def _signal_yield_event(
    item: AgentYield[object],
    attribution: AgentEventAttribution,
) -> ArtifactEvent | ModelError:
    payload = item.payload
    if not isinstance(payload, Progress):
        return ModelError(
            code=SIGNAL_PROJECTION_ERROR_CODE,
            message="Agent signal hook yielded an unsupported event shape",
            metadata={"yield_kind": item.kind.value},
        )
    identity = sha256(
        f"{payload.current_step or ''}:{payload.message}".encode()
    ).hexdigest()
    return ArtifactEvent(
        attribution=attribution,
        artifact_id=f"{attribution.run_id}:signal-progress:{identity}",
        name="signal_progress",
        content={
            "kind": item.kind.value,
            "message": payload.message,
            "current_step": payload.current_step,
            "metadata": payload.metadata,
        },
        metadata=payload.metadata,
    )


def _run_paused_event(
    state: AgentState,
    attribution: AgentEventAttribution,
) -> RunPausedEvent:
    approval = state.metadata.get("approval")
    approval_id: str | None = None
    tool_call_id: str | None = None
    allowed_decisions: tuple[str, ...] = ()
    event_metadata = dict(state.metadata)
    if isinstance(approval, Mapping):
        event_metadata = dict(approval)
        approval_id = _optional_mapping_text(approval, "id")
        tool_call_id = _optional_mapping_text(approval, "call_id")
        nested = approval.get("metadata")
        if tool_call_id is None and isinstance(nested, Mapping):
            tool_call_id = _optional_mapping_text(nested, "call_id")
        allowed_decisions = _string_tuple(approval.get("allowed_decisions"))
    return RunPausedEvent(
        attribution=attribution,
        reason=state.reason or AgentStateReason.USER_INTERRUPTED,
        prompt=state.current_activity or "Run paused.",
        state_id=state.id,
        approval_id=approval_id,
        tool_call_id=tool_call_id,
        allowed_decisions=allowed_decisions,
        metadata=event_metadata,
    )


def _cancel_error(item: AgentYield[object]) -> JsonObject:
    payload = item.payload
    if isinstance(payload, Cancel):
        metadata: dict[str, JsonValue] = dict(payload.metadata)
        if payload.requested_by is not None:
            metadata["requested_by"] = payload.requested_by
        return {
            "code": "cancelled",
            "message": payload.reason or "run cancelled",
            "metadata": metadata,
        }
    return {"code": "cancelled", "message": "run cancelled"}


def _state_error(state: AgentState) -> JsonObject:
    reason = state.reason.value if state.reason is not None else state.status.value
    return {
        "code": reason,
        "message": state.current_activity or reason,
        "metadata": {"state": state.status.value},
    }


def _state_model_error(state: AgentState) -> ModelError:
    reason = state.reason.value if state.reason is not None else state.status.value
    return ModelError(
        code=reason,
        message=state.current_activity or reason,
        metadata={"state": state.status.value},
    )


def _model_error_json(error: ModelError) -> JsonObject:
    return {
        "code": error.code,
        "message": error.message,
        "retryable": error.retryable,
        "metadata": error.metadata,
    }


def _error_yield(error: ModelError) -> AgentYield[object]:
    return AgentYield(
        kind=AgentYieldKind.ERROR,
        payload=Error(
            code=error.code,
            message=error.message,
            retryable=error.retryable,
            metadata=error.metadata,
        ),
    )


def _framework_error(
    code: str,
    message: str,
    error: AbstractSpakkyFrameworkError,
    context: _ExecutionContext | None = None,
) -> ModelError:
    metadata: JsonObject = {
        "framework_error": type(error).__name__,
    }
    if context is not None:
        metadata = {
            **context.counters,
            **context.route_metadata,
            **metadata,
        }
    return ModelError(code=code, message=message, metadata=metadata)


def _limit_error(
    code: str,
    message: str,
    context: _ExecutionContext,
) -> ModelError:
    return ModelError(
        code=code,
        message=message,
        metadata={**context.counters, **context.route_metadata},
    )


def _approval_unavailable_error(context: _ExecutionContext) -> ModelError:
    return ModelError(
        code="agent_approval_unavailable",
        message="Agent approval requires durable signal repositories",
        metadata=context.counters,
    )


def _routing_metadata(metadata: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        key: value
        for key in ("model_ref", "profile", "provider", "model")
        if (value := metadata.get(key)) is not None
    }


def _assistant_tool_message(
    content: str,
    calls: Sequence[ModelToolCall],
    routing: JsonObject,
) -> ModelMessage:
    tool_calls: list[JsonValue] = []
    for call in calls:
        tool_calls.append(
            {
                **dict(call.metadata),
                "id": _call_id(call),
                "name": call.name,
                "arguments": call.arguments,
            }
        )
    return ModelMessage(
        ModelMessageRole.ASSISTANT,
        content,
        metadata={**routing, "tool_calls": tool_calls},
    )


def _history_with_approved_call(
    history: Sequence[ModelMessage],
    call: ModelToolCall,
) -> tuple[ModelMessage, ...]:
    """Replace one assistant call envelope with its final approved invocation."""
    call_id = _call_id(call)
    updated = list(history)
    for message_index, message in enumerate(history):
        raw_calls = message.metadata.get("tool_calls")
        if message.role is not ModelMessageRole.ASSISTANT or not isinstance(
            raw_calls, Sequence
        ):
            continue
        calls = list(raw_calls)
        for call_index, raw_call in enumerate(raw_calls):
            if not isinstance(raw_call, Mapping) or raw_call.get("id") != call_id:
                continue
            calls[call_index] = {
                **dict(raw_call),
                **dict(call.metadata),
                "id": call_id,
                "name": call.name,
                "arguments": call.arguments,
            }
            updated[message_index] = replace(
                message,
                metadata={**message.metadata, "tool_calls": calls},
            )
            return tuple(updated)
    raise AgentDefinitionError(
        "Agent assistant history is missing the approved tool call"
    )


def _tool_result_message(call: ModelToolCall, result: JsonValue) -> ModelMessage:
    content = (
        result
        if isinstance(result, str)
        else dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )
    return ModelMessage(
        ModelMessageRole.TOOL,
        content,
        metadata={"call_id": _call_id(call), "tool_name": call.name},
    )


def _arguments_digest(arguments: JsonObject) -> str:
    try:
        encoded = dumps(
            arguments,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    except (TypeError, ValueError) as error:
        raise AgentDefinitionError(
            "Agent tool arguments are not deterministic JSON"
        ) from error
    return sha256(encoded).hexdigest()


def _context_metadata(context: _ExecutionContext) -> JsonObject:
    return {
        "history": [_message_metadata(message) for message in context.history],
        "assistant_text": list(context.assistant_text),
        "tool_calls": list(context.tool_calls),
        "step_count": context.step_count,
        "tool_call_count": context.tool_call_count,
        "total_tokens": context.total_tokens,
        "seen_call_ids": sorted(context.seen_call_ids),
        "approved_call_fingerprints": sorted(context.approved_call_fingerprints),
        "pending_calls": [_call_metadata(call) for call in context.pending_calls],
        "route_metadata": context.route_metadata,
    }


def _message_metadata(message: ModelMessage) -> JsonObject:
    return {
        "role": message.role.value,
        "content": message.content,
        "metadata": message.metadata,
    }


def _message_from_metadata(value: Mapping[str, JsonValue]) -> ModelMessage:
    role = value.get("role")
    content = value.get("content")
    metadata = value.get("metadata", {})
    if not isinstance(role, str) or not isinstance(content, str):
        raise AgentDefinitionError("Agent runner checkpoint message is invalid")
    if not isinstance(metadata, Mapping):
        raise AgentDefinitionError("Agent runner checkpoint metadata is invalid")
    try:
        message_role = ModelMessageRole(role)
    except ValueError as error:
        raise AgentDefinitionError("Agent runner checkpoint role is invalid") from error
    return ModelMessage(message_role, content, metadata=dict(metadata))


def _call_metadata(call: ModelToolCall) -> JsonObject:
    return {
        "name": call.name,
        "arguments": call.arguments,
        "call_id": call.call_id,
        "metadata": call.metadata,
    }


def _call_from_metadata(value: Mapping[str, JsonValue]) -> ModelToolCall:
    name = value.get("name")
    arguments = value.get("arguments")
    call_id = value.get("call_id")
    metadata = value.get("metadata", {})
    if not isinstance(name, str) or not isinstance(arguments, Mapping):
        raise AgentDefinitionError("Agent runner checkpoint tool call is invalid")
    if call_id is not None and not isinstance(call_id, str):
        raise AgentDefinitionError("Agent runner checkpoint call id is invalid")
    if not isinstance(metadata, Mapping):
        raise AgentDefinitionError("Agent runner checkpoint call metadata is invalid")
    return ModelToolCall(
        name=name,
        arguments=dict(arguments),
        call_id=call_id,
        metadata=dict(metadata),
    )


def _mapping_sequence(
    mapping: Mapping[str, JsonValue],
    key: str,
) -> tuple[Mapping[str, JsonValue], ...]:
    value = mapping.get(key, ())
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise AgentDefinitionError("Agent runner checkpoint sequence is invalid")
    result: list[Mapping[str, JsonValue]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise AgentDefinitionError("Agent runner checkpoint item is invalid")
        result.append(item)
    return tuple(result)


def _string_sequence(
    mapping: Mapping[str, JsonValue],
    key: str,
) -> tuple[str, ...]:
    value = mapping.get(key, ())
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise AgentDefinitionError("Agent runner checkpoint strings are invalid")
    if any(not isinstance(item, str) for item in value):
        raise AgentDefinitionError("Agent runner checkpoint string is invalid")
    return tuple(item for item in value if isinstance(item, str))


def _mapping_metadata(
    mapping: Mapping[str, JsonValue],
    key: str,
) -> Mapping[str, JsonValue]:
    value = mapping.get(key, {})
    if not isinstance(value, Mapping):
        raise AgentDefinitionError("Agent runner checkpoint mapping is invalid")
    return value


def _integer_metadata(mapping: Mapping[str, JsonValue], key: str) -> int:
    value = mapping.get(key, 0)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AgentDefinitionError("Agent runner checkpoint counter is invalid")
    return value


def _before_model(action_id: str) -> AgentActionBoundaryCheckpoint:
    return AgentActionBoundaryCheckpoint.before_model_call(
        action_id,
        idempotency=Idempotency.IDEMPOTENT,
    )


def _after_model(action_id: str) -> AgentActionBoundaryCheckpoint:
    return AgentActionBoundaryCheckpoint.after_model_call(
        action_id,
        idempotency=Idempotency.IDEMPOTENT,
    )


def _before_tool(
    descriptor: AgentToolDescriptor,
    call: ModelToolCall,
) -> AgentActionBoundaryCheckpoint:
    return AgentActionBoundaryCheckpoint.before_tool_call(
        f"tool:{_call_id(call)}",
        idempotency=descriptor.metadata.idempotency,
        metadata={"call_id": call.call_id or ""},
    )


def _after_tool(
    descriptor: AgentToolDescriptor,
    call: ModelToolCall,
) -> AgentActionBoundaryCheckpoint:
    return AgentActionBoundaryCheckpoint.after_tool_call(
        f"tool:{_call_id(call)}",
        idempotency=descriptor.metadata.idempotency,
        metadata={"call_id": call.call_id or ""},
    )


def _before_approval(
    call: ModelToolCall,
    descriptor: AgentToolDescriptor,
) -> AgentActionBoundaryCheckpoint:
    return AgentActionBoundaryCheckpoint.before_approval_wait(
        f"approval:{_call_id(call)}",
        metadata={"call_id": call.call_id or "", "tool": descriptor.schema.name},
    )


def _after_approval(
    call: ModelToolCall,
    descriptor: AgentToolDescriptor,
) -> AgentActionBoundaryCheckpoint:
    return AgentActionBoundaryCheckpoint.after_approval_wait(
        f"approval:{_call_id(call)}",
        metadata={"call_id": call.call_id or "", "tool": descriptor.schema.name},
    )


def _tool_result_json(result: object) -> JsonValue:
    """Serialize an arbitrary tool result into a JSON-compatible value.

    Tool callables return heterogeneous domain objects. The runner normalizes
    them neutrally rather than knowing any concrete tool's return type, unlike a
    hand-written loop that matches its own result dataclasses.
    """
    if result is None or isinstance(result, (bool, int, float, str)):
        return result
    if isinstance(result, DelegationToolResult):
        return {
            "summary": result.summary,
            "output": _tool_result_json(result.output),
            "metadata": _tool_result_json(result.metadata),
        }
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json")
    if is_dataclass(result) and not isinstance(result, type):
        return _tool_result_json(asdict(result))
    if isinstance(result, Mapping):
        return {str(key): _tool_result_json(item) for key, item in result.items()}
    if isinstance(result, Sequence) and not isinstance(result, (str, bytes)):
        return [_tool_result_json(item) for item in result]
    raise AgentToolDispatchError("Agent tool returned a non-serializable result")


def _optional_signal_text(signal: AgentSignal, name: str) -> str | None:
    value = signal.payload.get(name)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _optional_mapping_text(mapping: Mapping[str, JsonValue], name: str) -> str | None:
    value = mapping.get(name)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _string_tuple(value: JsonValue) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _call_id(call: ModelToolCall) -> str:
    """Resolve the stable tool-call id correlating a call's lifecycle events.

    ``ModelToolCall.call_id`` is the adapter-provided id that ties the
    ``start``/``args``/``end``/``result`` events of one call together. A model
    that omits it (``None``) gets a name-derived fallback so the lifecycle still
    shares one non-blank id, which the neutral attribution requires.
    """
    return call.call_id or f"call:{call.name}"
