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

from collections.abc import AsyncGenerator, Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass, replace

from pydantic import BaseModel

from spakky.agent.approval import (
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
from spakky.agent.delegation import DelegationToolResult
from spakky.agent.dispatcher import AgentToolDispatcher
from spakky.agent.error import (
    AgentModelConfigurationError,
    AgentPersistenceConfigurationError,
    AgentToolDispatchError,
)
from spakky.agent.event import (
    AgentEvent,
    AgentEventAttribution,
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
from spakky.agent.execution import Agent, RecoveryStrategy
from spakky.agent.hooks import AgentSignalHookDescriptor
from spakky.agent.inbound import RunAgentInput
from spakky.agent.interfaces.model import (
    IAgentModel,
    JsonSchemaConstraint,
    ModelError,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
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
        """Run one model-mediated loop, emitting the neutral event taxonomy.

        This is the lossless native stream AG-UI/A2A adapters consume (ADR-0013
        §3). It shares the run's orchestration with ``run()`` — model request,
        tool dispatch, durable approval gating, evidence persistence — but emits
        distinct ``AgentEvent`` members instead of coarse ``AgentYield`` items, so
        an adapter projects each event one-to-one rather than re-expanding framing.
        """
        attribution = self._event_attribution(run_input)
        state = (
            self._ensure_active_state(run_input, self.states)
            if self.states is not None
            else None
        )
        cursor = _MessageCursor(state_id=run_input.state_id)
        history = await self._resolved_history(run_input)
        yield RunStartedEvent(attribution)
        if state is not None:
            cancel = await self._consume_cancel(state)
            if cancel is not None:
                yield RunFinishedEvent(attribution, error=_cancel_error(cancel))
                return
        yield StepStartedEvent(attribution, step_name="model-call")
        async for event in self.model.stream(self._model_request(run_input, history)):
            if state is not None:
                cancel = await self._consume_cancel(state)
                if cancel is not None:
                    yield StepFinishedEvent(attribution, step_name="model-call")
                    yield RunFinishedEvent(attribution, error=_cancel_error(cancel))
                    return
            async for item in self._consume_stream_event_as_events(
                event, state, attribution, cursor
            ):
                yield item
            if event.kind is ModelStreamEventKind.ERROR and event.error is not None:
                yield StepFinishedEvent(attribution, step_name="model-call")
                yield RunFinishedEvent(
                    attribution,
                    error={"code": event.error.code, "message": event.error.message},
                )
                return
            if (
                state is not None
                and event.kind is ModelStreamEventKind.TOOL_CALL_CANDIDATE
                and event.tool_call is not None
                and self._states_required().get(state.id).status
                is not AgentStatus.ACTIVE
            ):
                current = self._states_required().get(state.id)
                yield StepFinishedEvent(attribution, step_name="model-call")
                if current.status is AgentStatus.INTERRUPTED:
                    yield _run_paused_event(current, attribution)
                    return
                yield RunFinishedEvent(attribution, error=_state_error(current))
                return
        yield StepFinishedEvent(attribution, step_name="model-call")
        # A tool that paused for approval already saved a WAIT_FOR_APPROVAL state
        # (INTERRUPTED, not ACTIVE); completing it would clobber the durable pause
        # the adapter surfaces as its deferred-tool request, so only an unpaused
        # (still ACTIVE) run transitions to COMPLETED — mirroring _run_durable.
        if (
            state is not None
            and self._states_required().get(state.id).status is AgentStatus.ACTIVE
        ):
            self._complete_state(state.id)
        elif state is not None:
            current = self._states_required().get(state.id)
            if current.status is AgentStatus.INTERRUPTED:
                yield _run_paused_event(current, attribution)
                return
            yield RunFinishedEvent(attribution, error=_state_error(current))
            return
        yield RunFinishedEvent(attribution)

    async def _consume_stream_event_as_events(
        self,
        event: ModelStreamEvent,
        state: AgentState | None,
        attribution: AgentEventAttribution,
        cursor: "_MessageCursor",
    ) -> AsyncGenerator[AgentEvent, None]:
        """Project one model stream event onto the neutral event taxonomy.

        The fine-grained C2 tool channels (``TOOL_CALL_START``/``ARGS_DELTA``/
        ``END``) project straight through as boundary events; ``TOOL_CALL_CANDIDATE``
        is the dispatch trigger that produces the ``ToolCallResultEvent`` after the
        tool runs (gated by the same durable approval flow ``run()`` uses).
        """
        match event.kind:
            case ModelStreamEventKind.TOKEN_DELTA:
                yield MessageDeltaEvent(
                    attribution,
                    message_id=cursor.message_id,
                    delta=event.token_delta or "",
                )
            case ModelStreamEventKind.MESSAGE_DELTA:
                yield MessageDeltaEvent(
                    attribution,
                    message_id=cursor.message_id,
                    delta=event.message_delta or "",
                )
            case ModelStreamEventKind.REASONING_DELTA:
                if self.model.capability.supports_reasoning:
                    yield ReasoningDeltaEvent(
                        attribution,
                        reasoning_id=cursor.reasoning_id,
                        delta=event.reasoning_delta or "",
                    )
            case ModelStreamEventKind.TOOL_CALL_START if event.tool_call is not None:
                yield ToolCallStartEvent(
                    attribution,
                    call_id=_call_id(event.tool_call),
                    tool_name=event.tool_call.name,
                    parent_message_id=cursor.message_id,
                )
            case ModelStreamEventKind.TOOL_CALL_ARGS_DELTA if (
                event.tool_call is not None
            ):
                yield ToolCallArgsDeltaEvent(
                    attribution,
                    call_id=_call_id(event.tool_call),
                    args_delta=event.tool_call_args_delta or "",
                )
            case ModelStreamEventKind.TOOL_CALL_END if event.tool_call is not None:
                yield ToolCallEndEvent(attribution, call_id=_call_id(event.tool_call))
            case ModelStreamEventKind.TOOL_CALL_CANDIDATE if (
                event.tool_call is not None
            ):
                async for item in self._dispatch_tool_call_event(
                    state, event.tool_call, attribution, cursor
                ):
                    yield item
            case _:
                return

    async def _dispatch_tool_call_event(
        self,
        state: AgentState | None,
        call: ModelToolCall,
        attribution: AgentEventAttribution,
        cursor: "_MessageCursor",
    ) -> AsyncGenerator[AgentEvent, None]:
        """Dispatch a complete tool call and emit its neutral result event.

        Mirrors ``_execute_tool_call`` but emits ``ToolCallResultEvent`` instead of
        an ``AgentYield``. Durable approval gating and evidence persistence are the
        same shared steps, so an unapproved call dispatches nothing and emits no
        result (the adapter surfaces approval as its own deferred-tool idiom).
        """
        descriptor = self.agent.tool_catalog.by_schema_name(call.name)
        if state is not None:
            _, _, cleared = self._resolve_approval(state, descriptor, call)
            if not cleared:
                return
            self._append_boundary(state.id, _before_tool(descriptor, call))
        result_object = await self._dispatch(call, attribution)
        if isinstance(result_object, DelegationToolResult):
            for child_event in result_object.events:
                yield child_event
        result = _tool_result_json(result_object)
        if state is not None:
            self._append_boundary(state.id, _after_tool(descriptor, call))
            self._append_tool_evidence(state.id, descriptor, result)
        yield ToolCallResultEvent(
            attribution,
            call_id=_call_id(call),
            tool_name=call.name,
            message_id=cursor.message_id,
            result=result,
        )

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

    def _complete_state(self, state_id: str) -> None:
        self._states_required().save(
            replace(
                self._states_required().get(state_id),
                status=AgentStatus.COMPLETED,
                transition=AgentStateTransition.COMPLETED,
                current_activity="run completed",
            )
        )

    async def _run_stateless(
        self,
        run_input: RunAgentInput,
    ) -> AsyncGenerator[AgentYield[object], None]:
        tool_calls: list[str] = []
        assistant_text: list[str] = []
        yield _progress("preparing model request", "model")
        history = await self._resolved_history(run_input)
        async for event in self.model.stream(self._model_request(run_input, history)):
            async for item in self._consume_stream_event(
                event, None, tool_calls, assistant_text
            ):
                yield item
            if event.kind is ModelStreamEventKind.ERROR and event.error is not None:
                return
        self._persist_turns(run_input, assistant_text)
        yield self._final_yield(run_input.state_id, tool_calls, evidence_count=0)

    async def _run_durable(
        self,
        run_input: RunAgentInput,
        states: IAgentStateRepository,
    ) -> AsyncGenerator[AgentYield[object], None]:
        # Phase 1: ensure an active durable state for the run.
        state = self._ensure_active_state(run_input, states)

        # Phase 2: replay resume plan from persisted evidence when requested.
        if run_input.resume:
            yield self._emit_resume_plan(state)
            state = states.get(run_input.state_id)

        # Phase 3: honor a cancel signal queued before the model loop.
        cancel = await self._consume_cancel(state)
        if cancel is not None:
            yield cancel
            return

        # Phase 4: open the model action boundary and request the model.
        tool_calls: list[str] = []
        assistant_text: list[str] = []
        yield _progress("preparing model request", "model")
        self._append_boundary(state.id, _before_model(self._model_action_id()))
        request = self._model_request(
            run_input, await self._resolved_history(run_input)
        )

        # Phase 5: consume the provider-neutral model stream.
        async for event in self.model.stream(request):
            cancel = await self._consume_cancel(state)
            if cancel is not None:
                yield cancel
                return
            async for signal_item in self._consume_inbound_signals(state):
                yield signal_item
            terminated = False
            async for item in self._consume_stream_event(
                event, state, tool_calls, assistant_text
            ):
                yield item
            if event.kind is ModelStreamEventKind.ERROR and event.error is not None:
                return
            if (
                event.kind is ModelStreamEventKind.TOOL_CALL_CANDIDATE
                and event.tool_call is not None
                and states.get(state.id).status is not AgentStatus.ACTIVE
            ):
                terminated = True
            if terminated:
                return

        # Phase 6: transition to a terminal completed state and emit the final.
        final_state = states.save(
            replace(
                states.get(state.id),
                status=AgentStatus.COMPLETED,
                transition=AgentStateTransition.COMPLETED,
                current_activity="run completed",
            )
        )
        self._persist_turns(run_input, assistant_text)
        yield self._final_yield(
            final_state.id,
            tool_calls,
            evidence_count=self._evidence_count(final_state.id),
        )

    async def _consume_stream_event(
        self,
        event: ModelStreamEvent,
        state: AgentState | None,
        tool_calls: list[str],
        assistant_text: list[str],
    ) -> AsyncGenerator[AgentYield[object], None]:
        """Translate one model stream event into the public yield vocabulary.

        Assistant-visible text (token and message deltas, not reasoning) is
        accumulated into ``assistant_text`` so the completed run can persist the
        assistant turn into the conversation transcript (ADR-0013 §6).
        """
        match event.kind:
            case ModelStreamEventKind.TOKEN_DELTA:
                assistant_text.append(event.token_delta or "")
                yield _token(event.token_delta or "")
            case ModelStreamEventKind.MESSAGE_DELTA:
                assistant_text.append(event.message_delta or "")
                yield _token(event.message_delta or "")
            case ModelStreamEventKind.REASONING_DELTA:
                if self.model.capability.supports_reasoning:
                    yield _token(event.reasoning_delta or "")
            case ModelStreamEventKind.TOOL_CALL_CANDIDATE if (
                event.tool_call is not None
            ):
                async for item in self._execute_tool_call(state, event.tool_call):
                    yield item
                tool_calls.append(event.tool_call.name)
            case ModelStreamEventKind.DONE:
                if state is not None:
                    self._append_boundary(
                        state.id, _after_model(self._model_action_id())
                    )
            case ModelStreamEventKind.ERROR if event.error is not None:
                yield self._fail_on_model_error(state, event.error)
            case _:
                return

    async def _execute_tool_call(
        self,
        state: AgentState | None,
        call: ModelToolCall,
    ) -> AsyncGenerator[AgentYield[object], None]:
        descriptor = self.agent.tool_catalog.by_schema_name(call.name)
        if state is not None:
            approval_item, _, cleared = self._resolve_approval(state, descriptor, call)
            if approval_item is not None:
                yield approval_item
            if not cleared:
                return
            self._append_boundary(state.id, _before_tool(descriptor, call))
        result_object = await self._dispatch(
            call,
            AgentEventAttribution(
                agent_id=self._agent_type(),
                run_id=state.id if state is not None else _call_id(call),
                conversation_id=state.id if state is not None else _call_id(call),
            ),
        )
        result = _tool_result_json(result_object)
        if state is not None:
            self._append_boundary(state.id, _after_tool(descriptor, call))
            yield _evidence_yield(
                self._append_tool_evidence(state.id, descriptor, result)
            )
        yield _tool_yield(descriptor, call, result)

    def _resolve_approval(
        self,
        state: AgentState,
        descriptor: AgentToolDescriptor,
        call: ModelToolCall,
    ) -> tuple[AgentYield[object] | None, AgentApprovalRequest | None, bool]:
        """Drive the HITL pause -> approval-request -> resume flow for one call.

        Returns ``(approval_item, request, cleared)``: the approval request to
        surface (or ``None`` when no approval is needed), its durable request
        envelope, and whether the tool may now proceed. ``cleared`` is decided by
        the durable approval decision polled from the signal queue, the
        non-blocking resume the ADR-0013 §5 flow uses.
        """
        plan = plan_agent_tool_approval(
            descriptor=descriptor,
            approval_id=self._approval_id(state.id, call),
            agent_state_id=state.id,
            agent_type=self._agent_type(),
            call_id=call.call_id,
        )
        if not (plan.requires_approval and plan.yield_item is not None):
            return None, None, True
        self._append_boundary(state.id, _before_approval(call, descriptor))
        # plan_agent_tool_approval pairs state with yield_item for WAIT_FOR_APPROVAL.
        if plan.state is not None:  # pragma: no branch - state paired with yield_item
            self._states_required().save(plan.state)
        approval_item = AgentYield[object](
            kind=plan.yield_item.kind,
            payload=plan.yield_item.payload,
        )
        cleared = self._consume_approval(state.id, plan.request)
        if cleared:
            self._append_boundary(state.id, _after_approval(call, descriptor))
        return approval_item, plan.request, cleared

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
            self._states_required().save(
                replace(
                    current,
                    status=AgentStatus.FAILED,
                    transition=AgentStateTransition.FAILED,
                    reason=AgentStateReason.EXECUTION_FAILED,
                    current_activity="model stream failed",
                    metadata={**current.metadata, "model_error_code": error.code},
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
                ModelMessage(ModelMessageRole.USER, run_input.instruction),
            ),
            tool_calling=tool_calling,
            sampling=DEFAULT_SAMPLING,
            metadata={"state_id": run_input.state_id, **run_input.metadata},
        )

    async def _resolved_history(
        self,
        run_input: RunAgentInput,
    ) -> tuple[ModelMessage, ...]:
        """Resolve prior-turn messages and apply declared compaction (ADR-0013 §7).

        The raw history is resolved first, then the agent's declared compaction
        chain is applied so the seeded transcript stays within the backend's
        context window before it reaches the model request.
        """
        return await self._compact_history(self._resolve_history(run_input))

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
    ) -> tuple[ModelMessage, ...]:
        """Apply the declared compaction chain when the token estimate trips it.

        Compaction runs only when an agent declares a policy and the running token
        estimate of the resolved history crosses ``trigger_token_threshold`` — a
        short conversation is sent verbatim. The estimate and the backend
        ``ModelCapability`` are passed to each strategy so a strategy can scale its
        effect, then each strategy's output is threaded into the next (chain order
        is compaction order).
        """
        policy = self.agent.spec.compaction
        if policy is None:
            return history
        usage = ModelUsage(total_tokens=_estimate_token_count(history))
        if (usage.total_tokens or 0) < policy.trigger_token_threshold:
            return history
        capability = self.model.capability
        for strategy in policy.strategies:
            history = await strategy.compact(history, usage, capability)
        return history

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
                    reason=completed.reason.value if completed.reason else None,
                    requested_by=_optional_signal_text(signal, "requested_by"),
                    metadata={"state": completed.status.value},
                ),
            )
        return None

    async def _consume_inbound_signals(
        self,
        state: AgentState,
    ) -> AsyncGenerator[AgentYield[object], None]:
        """Dispatch pending non-terminal signals at the model-stream poll point.

        Cancel and approval decisions own dedicated phases, so this poll handles
        the remaining inbound kinds. A declarative ``@on_signal`` hook, when one
        is declared for the kind, owns the reaction and its yielded items flow
        into the public stream. A ``USER_MESSAGE`` with no declared hook falls
        back to the built-in progress item so the default loop still observes the
        message. Other kinds with no hook stay pending for a later poll rather
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

    def _consume_approval(
        self,
        state_id: str,
        request: AgentApprovalRequest | None,
    ) -> bool:
        for signal in self._signals_required().list_pending(state_id):
            if signal.kind is not AgentSignalKind.APPROVAL_DECISION:
                continue
            if (
                request is not None
                and _optional_signal_text(signal, "request_id") != request.id
            ):
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
                    },
                    summary="approval decision consumed",
                ),
            )
            return outcome.decision in (
                ApprovalDecision.APPROVE,
                ApprovalDecision.MODIFY,
            )
        return False

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

    def _model_action_id(self) -> str:
        return f"model:{self._agent_type()}_decision"

    def _approval_id(self, state_id: str, call: ModelToolCall) -> str:
        return f"approval:{state_id}:{call.name}"

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
    right message. One assistant message block and one reasoning block per run are
    sufficient for the framework-owned single-step loop, so the ids are derived
    deterministically from the run id rather than counted per delta.
    """

    state_id: str

    @property
    def message_id(self) -> str:
        return f"{self.state_id}:message"

    @property
    def reasoning_id(self) -> str:
        return f"{self.state_id}:reasoning"


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


def _token(text: str) -> AgentYield[object]:
    return AgentYield(kind=AgentYieldKind.TOKEN, payload=Token(text))


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
        f"tool:{call.name}",
        idempotency=descriptor.metadata.idempotency,
        metadata={"call_id": call.call_id or ""},
    )


def _after_tool(
    descriptor: AgentToolDescriptor,
    call: ModelToolCall,
) -> AgentActionBoundaryCheckpoint:
    return AgentActionBoundaryCheckpoint.after_tool_call(
        f"tool:{call.name}",
        idempotency=descriptor.metadata.idempotency,
        metadata={"call_id": call.call_id or ""},
    )


def _before_approval(
    call: ModelToolCall,
    descriptor: AgentToolDescriptor,
) -> AgentActionBoundaryCheckpoint:
    return AgentActionBoundaryCheckpoint.before_approval_wait(
        f"approval:{call.name}",
        metadata={"call_id": call.call_id or "", "tool": descriptor.schema.name},
    )


def _after_approval(
    call: ModelToolCall,
    descriptor: AgentToolDescriptor,
) -> AgentActionBoundaryCheckpoint:
    return AgentActionBoundaryCheckpoint.after_approval_wait(
        f"approval:{call.name}",
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
