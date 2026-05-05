"""Acceptance tests for ADR-0009 core agent contracts."""

from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from dataclasses import dataclass
from typing import override

from spakky.agent import (
    IAgentEvidenceRepository,
    IAgentModel,
    IAgentSignalRepository,
    IAgentStateRepository,
    Agent,
    AgentEvidence,
    AgentEvidenceCandidate,
    AgentEvidenceKind,
    AgentExecutionSpec,
    AgentSignal,
    AgentSignalKind,
    AgentState,
    AgentStateTransition,
    AgentStatus,
    AgentYield,
    AgentYieldKind,
    Evidence,
    EvidenceCapture,
    Final,
    Idempotency,
    JsonSchemaConstraint,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    ModelToolChoice,
    ModelToolSpec,
    Progress,
    RecoveryStrategy,
    Token,
    Tool,
    ToolApprovalRequirement,
    ToolCallingSpec,
    ToolEffects,
    agent_tool,
)
from spakky.agent.error import AgentDefinitionError


@dataclass(frozen=True, slots=True)
class _AgentCommand:
    state_id: str
    instruction: str


@dataclass(frozen=True, slots=True)
class _AgentResult:
    answer: str


@dataclass(frozen=True, slots=True)
class _WorkspaceReadResult:
    path: str
    include_metadata: bool


@Agent(
    spec=AgentExecutionSpec(
        name="adr0009_acceptance_agent",
        accepted_signals=(AgentSignalKind.USER_MESSAGE,),
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
    )
)
class _AcceptanceAgent:
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
        schema_name="workspace.read",
        description="Read a workspace path.",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def read_workspace(
        self,
        path: str,
        include_metadata: bool = False,
    ) -> _WorkspaceReadResult:
        return _WorkspaceReadResult(path=path, include_metadata=include_metadata)

    async def execute(
        self,
        command: _AgentCommand,
    ) -> AsyncGenerator[AgentYield[object], None]:
        self._states.save(
            AgentState(
                id=command.state_id,
                agent_type="AcceptanceAgent",
                status=AgentStatus.ACTIVE,
                transition=AgentStateTransition.RUNNING,
                current_activity=command.instruction,
                pending_signal_count=len(self._signals.list_pending(command.state_id)),
            )
        )
        yield AgentYield(
            kind=AgentYieldKind.PROGRESS,
            payload=Progress("model request prepared", current_step="model"),
        )
        request = self._request(command)
        async for event in self._model.stream(request):
            if event.kind is ModelStreamEventKind.TOKEN_DELTA:
                yield AgentYield(
                    kind=AgentYieldKind.TOKEN,
                    payload=Token(event.token_delta or ""),
                )
            if (
                event.kind is ModelStreamEventKind.TOOL_CALL_CANDIDATE
                and event.tool_call is not None
            ):
                descriptor = Agent.get(_AcceptanceAgent).tool_catalog.by_schema_name(
                    event.tool_call.name
                )
                evidence = AgentEvidenceCandidate.tool_result(
                    tool_identity=descriptor.identity.key,
                    tool_schema_name=descriptor.schema.name,
                    result=event.tool_call.arguments,
                    capture=descriptor.metadata.evidence,
                    summary="tool candidate accepted",
                ).to_evidence(
                    evidence_id=f"{command.state_id}:evidence:1",
                    agent_state_id=command.state_id,
                )
                self._evidence.append(evidence)
                yield AgentYield(
                    kind=AgentYieldKind.TOOL,
                    payload=Tool(
                        name=event.tool_call.name,
                        call_id=event.tool_call.call_id,
                        arguments=event.tool_call.arguments,
                    ),
                )
                yield AgentYield(
                    kind=AgentYieldKind.EVIDENCE,
                    payload=Evidence(evidence=evidence),
                )
        self._states.save(
            AgentState(
                id=command.state_id,
                agent_type="AcceptanceAgent",
                status=AgentStatus.COMPLETED,
                transition=AgentStateTransition.COMPLETED,
            )
        )
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(output=_AgentResult("done"), metadata={}),
        )

    def _request(self, command: _AgentCommand) -> ModelRequest:
        descriptor = Agent.get(_AcceptanceAgent).tool_catalog.by_schema_name(
            "workspace.read"
        )
        return ModelRequest(
            messages=(
                ModelMessage(ModelMessageRole.SYSTEM, "Use typed tools."),
                ModelMessage(ModelMessageRole.USER, command.instruction),
            ),
            tool_calling=ToolCallingSpec(
                tools=(
                    ModelToolSpec(
                        name=descriptor.schema.name,
                        description=descriptor.description,
                        parameters=JsonSchemaConstraint(
                            schema=descriptor.schema.input_schema
                        ),
                        metadata={"tool_identity": descriptor.identity.key},
                    ),
                ),
                choice=ModelToolChoice.REQUIRED,
            ),
        )


async def test_adr0009_core_contract_acceptance_expect_agent_stream_model_tool_and_state() -> (
    None
):
    """ADR-0009 core contract가 @Agent부터 state/evidence stream까지 조립된다."""
    model = _ScriptedModel(
        (
            ModelStreamEvent(
                kind=ModelStreamEventKind.TOKEN_DELTA,
                token_delta="reading",
            ),
            ModelStreamEvent(
                kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
                tool_call=ModelToolCall(
                    name="workspace.read",
                    arguments={"path": "README.md", "include_metadata": True},
                    call_id="call-1",
                ),
            ),
            ModelStreamEvent(kind=ModelStreamEventKind.DONE),
        )
    )
    states = _StateRepository()
    signals = _SignalRepository(
        (
            AgentSignal(
                id="signal-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.USER_MESSAGE,
                payload={"message": "continue"},
            ),
        )
    )
    evidence = _EvidenceRepository()
    agent = _AcceptanceAgent(model, states, signals, evidence)

    items = [item async for item in agent.execute(_AgentCommand("run-1", "inspect"))]

    assert Agent.get(_AcceptanceAgent).spec.name == "adr0009_acceptance_agent"
    assert Agent.get(_AcceptanceAgent).required_persistence_repository_types() == (
        IAgentStateRepository,
        IAgentSignalRepository,
        IAgentEvidenceRepository,
    )
    descriptor = Agent.get(_AcceptanceAgent).tool_catalog.by_schema_name(
        "workspace.read"
    )
    assert descriptor.schema.input_schema == {
        "type": "object",
        "title": "workspace.read.input",
        "properties": {
            "path": {"type": "string"},
            "include_metadata": {"type": "boolean"},
        },
        "additionalProperties": False,
        "required": ["path"],
    }
    assert model.requests[0].tool_calling is not None
    assert model.requests[0].tool_calling.tools[0].parameters.schema is (
        descriptor.schema.input_schema
    )
    assert [item.kind for item in items] == [
        AgentYieldKind.PROGRESS,
        AgentYieldKind.TOKEN,
        AgentYieldKind.TOOL,
        AgentYieldKind.EVIDENCE,
        AgentYieldKind.FINAL,
    ]
    assert states.get("run-1").status is AgentStatus.COMPLETED
    assert signals.list_pending("run-1")[0].kind is AgentSignalKind.USER_MESSAGE
    assert evidence.list_by_state("run-1")[0].kind is AgentEvidenceKind.TOOL


class _ScriptedModel(IAgentModel):
    def __init__(self, events: Sequence[ModelStreamEvent]) -> None:
        self._events = tuple(events)
        self.requests: list[ModelRequest] = []

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(content="complete")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        for event in self._events:
            yield event


class _StateRepository(IAgentStateRepository):
    def __init__(self) -> None:
        self._states: dict[str, AgentState] = {}

    @override
    def get(self, state_id: str) -> AgentState:
        state = self.get_or_none(state_id)
        if state is None:
            raise AgentDefinitionError("Missing acceptance state")
        return state

    @override
    def get_or_none(self, state_id: str) -> AgentState | None:
        return self._states.get(state_id)

    @override
    def save(self, state: AgentState) -> AgentState:
        self._states[state.id] = state
        return state

    @override
    def list_by_status(self, status: AgentStatus) -> Sequence[AgentState]:
        return tuple(state for state in self._states.values() if state.status is status)

    @override
    def list_resume_candidates(self) -> Sequence[AgentState]:
        return tuple(
            state
            for state in self._states.values()
            if state.status in (AgentStatus.ACTIVE, AgentStatus.INTERRUPTED)
        )


class _SignalRepository(IAgentSignalRepository):
    def __init__(self, signals: Sequence[AgentSignal]) -> None:
        self._signals = tuple(signals)
        self._consumed: set[str] = set()

    @override
    def append(self, signal: AgentSignal) -> AgentSignal:
        self._signals = (*self._signals, signal)
        return signal

    @override
    def list_pending(self, state_id: str) -> Sequence[AgentSignal]:
        return tuple(
            signal
            for signal in self._signals
            if signal.agent_state_id == state_id and signal.id not in self._consumed
        )

    @override
    def mark_consumed(self, signal_id: str) -> AgentSignal:
        for signal in self._signals:
            if signal.id == signal_id:
                self._consumed.add(signal_id)
                return signal
        raise AgentDefinitionError("Missing acceptance signal")


class _EvidenceRepository(IAgentEvidenceRepository):
    def __init__(self) -> None:
        self._evidence: dict[str, AgentEvidence] = {}

    @override
    def append(self, evidence: AgentEvidence) -> AgentEvidence:
        self._evidence[evidence.id] = evidence
        return evidence

    @override
    def get(self, evidence_id: str) -> AgentEvidence:
        evidence = self._evidence.get(evidence_id)
        if evidence is None:
            raise AgentDefinitionError("Missing acceptance evidence")
        return evidence

    @override
    def list_by_state(self, state_id: str) -> Sequence[AgentEvidence]:
        return tuple(
            artifact
            for artifact in self._evidence.values()
            if artifact.agent_state_id == state_id
        )

    @override
    def list_by_manifest_ref(self, manifest_ref: str) -> Sequence[AgentEvidence]:
        return tuple(
            artifact
            for artifact in self._evidence.values()
            if artifact.manifest_ref == manifest_ref
        )
