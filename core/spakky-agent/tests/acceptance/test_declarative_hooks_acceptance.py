"""Acceptance test: declarative @on_signal hook through the application container.

This is the issue #413 acceptance scenario: an @Agent that declares only a spec,
@agent_tool capabilities, and one @on_signal(STEERING_INSTRUCTION) hook — with no
execute() body — runs the full framework-owned loop when resolved through the
Spakky application container. The run exercises tool dispatch, the unified HITL
pause -> approval-decision -> resume flow (ADR-0013 §5), the declarative steering
hook surfacing its own stream item at the model-stream poll point, and a typed
COMPLETED termination.
"""

from collections.abc import AsyncGenerator, AsyncIterator, Sequence
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
    AgentExecutionLimits,
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
    Progress,
    RecoveryStrategy,
    RunAgentInput,
    Tool,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
    on_signal,
)
from spakky.agent.error import AgentDefinitionError
from spakky.agent.main import initialize


@dataclass(frozen=True, slots=True)
class NoteResult:
    """Structured tool result for the declarative hook acceptance agent."""

    note: str


@Agent(
    spec=AgentExecutionSpec(
        name="steering_assistant",
        objective="run the framework loop reacting to a declarative steering hook",
        accepted_signals=(
            AgentSignalKind.USER_MESSAGE,
            AgentSignalKind.APPROVAL_DECISION,
            AgentSignalKind.CANCEL,
            AgentSignalKind.STEERING_INSTRUCTION,
        ),
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
        limits=AgentExecutionLimits(timeout_seconds=600),
    )
)
class SteeringAssistant:
    """Declarative agent: spec + tools + one @on_signal hook, no execute() body."""

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

    @on_signal(AgentSignalKind.STEERING_INSTRUCTION)
    async def on_steering(
        self,
        signal: AgentSignal,
    ) -> AsyncGenerator[AgentYield[object], None]:
        """Surface a mid-run steering instruction back into the public stream."""
        instruction = signal.payload.get("instruction")
        text = instruction if isinstance(instruction, str) else ""
        yield AgentYield(
            kind=AgentYieldKind.PROGRESS,
            payload=Progress(
                f"steering instruction: {text}",
                current_step="steering",
                metadata={"signal_id": signal.id},
            ),
        )

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


async def test_declarative_steering_hook_runs_tools_hitl_and_termination() -> None:
    """spec+tools+@on_signal만 선언한 Agent가 컨테이너 경유로 도구·HITL·훅·종료를 자동 실행한다."""
    app = SpakkyApplication(ApplicationContext())
    initialize(app)
    app.add(ScriptedModel)
    app.add(MemoryStateRepository)
    app.add(MemorySignalRepository)
    app.add(MemoryEvidenceRepository)
    app.add(SteeringAssistant)
    app.start()

    signals = app.container.get(IAgentSignalRepository)
    states = app.container.get(IAgentStateRepository)
    evidence = app.container.get(IAgentEvidenceRepository)
    signals.append(
        AgentSignal(
            id="approval:run-1:note.write",
            agent_state_id="run-1",
            kind=AgentSignalKind.APPROVAL_DECISION,
            payload={
                "request_id": "approval:run-1:note.write",
                "decision": ApprovalDecision.APPROVE.value,
            },
        )
    )
    signals.append(
        AgentSignal(
            id="steer:run-1",
            agent_state_id="run-1",
            kind=AgentSignalKind.STEERING_INSTRUCTION,
            payload={"instruction": "keep the note short"},
        )
    )

    assistant = app.container.get(SteeringAssistant)
    execute = vars(SteeringAssistant)["execute"]
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
    assert any(
        item.kind is AgentYieldKind.PROGRESS
        and isinstance(item.payload, Progress)
        and item.payload.current_step == "steering"
        and "keep the note short" in item.payload.message
        for item in items
    )
    assert signals.list_pending("run-1") == ()
    assert states.get("run-1").status is AgentStatus.COMPLETED
    assert {artifact.kind for artifact in evidence.list_by_state("run-1")} >= {
        AgentEvidenceKind.ACTION_BOUNDARY,
        AgentEvidenceKind.APPROVAL,
        AgentEvidenceKind.EVALUATION,
        AgentEvidenceKind.TOOL,
    }
    final = items[-1].payload
    assert isinstance(final, Final)
    app.stop()


@Pod()
class ScriptedModel(IAgentModel):
    """Scripted model streaming a token, two tool calls, then done."""

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="scripted")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
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
