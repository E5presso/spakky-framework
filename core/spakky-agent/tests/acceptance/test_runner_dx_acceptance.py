"""Acceptance test: declaration-only @Agent runs tools + HITL + termination.

This is the SC-1 acceptance scenario for issue #410: an @Agent that declares
only a spec plus @agent_tool methods (no execute() body) runs the full
framework-owned loop — model stream, automatic tool dispatch, the unified HITL
pause -> approval-request -> resume flow, and typed termination — when resolved
and invoked through the Spakky application container exactly like a UseCase.
"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import override

from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod

from spakky.agent import (
    IAgentEvidenceRepository,
    IAgentModel,
    IAgentSignalRepository,
    IAgentStateRepository,
    Agent,
    AgentEvidence,
    AgentEvidenceKind,
    AgentExecutionSpec,
    AgentSignal,
    AgentSignalKind,
    AgentState,
    AgentStatus,
    AgentYield,
    AgentYieldKind,
    Approval,
    ApprovalDecision,
    EvidenceCapture,
    Final,
    Idempotency,
    ModelCapability,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    RecoveryStrategy,
    RunAgentInput,
    Tool,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
)
from spakky.agent.error import AgentDefinitionError
from spakky.agent.main import initialize
from spakky.agent.runner import _arguments_digest


@dataclass(frozen=True, slots=True)
class NoteResult:
    """Structured tool result for the acceptance agent."""

    note: str


@Agent(
    spec=AgentExecutionSpec(
        name="declarative_assistant",
        objective="run the framework loop from declaration only",
        accepted_signals=(
            AgentSignalKind.USER_MESSAGE,
            AgentSignalKind.APPROVAL_DECISION,
            AgentSignalKind.CANCEL,
        ),
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
    )
)
class DeclarativeAssistant:
    """Agent declaring only a spec and tools — execute() is auto-provided."""

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
        schema_name="note.read",
        description="Read a note without approval.",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def note_read(self, topic: str) -> NoteResult:
        """Read a note for a topic."""
        return NoteResult(note=f"read:{topic}")

    @agent_tool(
        schema_name="note.write",
        description="Write a note after human approval.",
        effects=ToolEffects.write_state(),
        idempotency=Idempotency.CONDITIONALLY_IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.REQUIRED,
    )
    def note_write(self, topic: str) -> NoteResult:
        """Write a note for a topic after approval."""
        return NoteResult(note=f"write:{topic}")


async def test_declaration_only_agent_runs_tools_hitl_and_termination() -> None:
    """spec과 @agent_tool만 선언한 Agent가 컨테이너 경유로 전 루프를 자동 실행한다."""
    app = SpakkyApplication(ApplicationContext())
    initialize(app)
    app.add(ScriptedModel)
    app.add(MemoryStateRepository)
    app.add(MemorySignalRepository)
    app.add(MemoryEvidenceRepository)
    app.add(DeclarativeAssistant)
    app.start()

    signals = app.container.get(IAgentSignalRepository)
    states = app.container.get(IAgentStateRepository)
    evidence = app.container.get(IAgentEvidenceRepository)
    approval_id = "approval:run-1:write-1:" + _arguments_digest({"topic": "agents"})
    signals.append(
        AgentSignal(
            id=approval_id,
            agent_state_id="run-1",
            kind=AgentSignalKind.APPROVAL_DECISION,
            payload={
                "request_id": approval_id,
                "decision": ApprovalDecision.APPROVE.value,
            },
        )
    )

    assistant = app.container.get(DeclarativeAssistant)
    execute = vars(DeclarativeAssistant)["execute"]
    items: list[AgentYield[object]] = []
    async for item in execute(
        assistant,
        RunAgentInput(state_id="run-1", instruction="take a small note"),
    ):
        items.append(item)

    kinds = {item.kind for item in items}
    assert {
        AgentYieldKind.TOKEN,
        AgentYieldKind.APPROVAL,
        AgentYieldKind.TOOL,
        AgentYieldKind.EVIDENCE,
        AgentYieldKind.FINAL,
    } <= kinds
    assert sum(1 for item in items if isinstance(item.payload, Approval)) == 1
    assert [item.payload.name for item in items if isinstance(item.payload, Tool)] == [
        "note.read",
        "note.write",
    ]
    assert states.get("run-1").status is AgentStatus.COMPLETED
    assert {artifact.kind for artifact in evidence.list_by_state("run-1")} >= {
        AgentEvidenceKind.ACTION_BOUNDARY,
        AgentEvidenceKind.APPROVAL,
        AgentEvidenceKind.TOOL,
    }
    final = items[-1].payload
    assert isinstance(final, Final)
    app.stop()


@Pod()
class ScriptedModel(IAgentModel):
    """Scripted model streaming a token, two tool calls, then done."""

    def __init__(self) -> None:
        self._request_count = 0

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="scripted")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        if self._request_count > 0:
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.TOKEN_DELTA,
                token_delta="done",
            )
            yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)
            return
        self._request_count += 1
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOKEN_DELTA,
            token_delta="planning",
        )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
            tool_call=ModelToolCall(
                name="note.read",
                arguments={"topic": "agents"},
                call_id="read-1",
            ),
        )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
            tool_call=ModelToolCall(
                name="note.write",
                arguments={"topic": "agents"},
                call_id="write-1",
            ),
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


@Pod()
class MemoryStateRepository(IAgentStateRepository):
    """In-memory state repository for the acceptance scenario."""

    def __init__(self) -> None:
        self._states: dict[str, AgentState] = {}

    @override
    def get(self, state_id: str) -> AgentState:
        state = self._states.get(state_id)
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
        return ()


@Pod()
class MemorySignalRepository(IAgentSignalRepository):
    """In-memory signal repository for the acceptance scenario."""

    def __init__(self) -> None:
        self._signals: tuple[AgentSignal, ...] = ()
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


@Pod()
class MemoryEvidenceRepository(IAgentEvidenceRepository):
    """In-memory evidence repository for the acceptance scenario."""

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
        return ()
