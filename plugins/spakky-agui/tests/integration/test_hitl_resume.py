"""Integration: deferred-tool HITL surfaces an approval and resumes on decision.

Run 1 reaches a REQUIRED-approval tool, pauses, and streams the deferred
``hitl_approval`` tool frame with no result. Run 2 POSTs the human decision; the
endpoint ingests it as a durable signal and the runner resumes from the paused
boundary. APPROVE proceeds to the tool result and RUN_FINISHED; REJECT
terminates without a tool result.
"""

from collections.abc import AsyncIterator, Sequence
from json import loads
from typing import override

from ag_ui.core import RunAgentInput as AgUiRunAgentInput
from ag_ui.encoder import EventEncoder
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spakky.agent import (
    Agent,
    AgentEvidence,
    AgentExecutionSpec,
    AgentRunner,
    AgentSignal,
    AgentSignalKind,
    AgentState,
    AgentStatus,
    EvidenceCapture,
    Idempotency,
    ModelCapability,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    RecoveryStrategy,
    RunAgentInput,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
)
from spakky.agent.error import AgentDefinitionError
from spakky.agent.interfaces.model import IAgentModel
from spakky.agent.interfaces.repository import (
    IAgentEvidenceRepository,
    IAgentSignalRepository,
    IAgentStateRepository,
)

from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.endpoint import add_agui_endpoint
from spakky.plugins.agui.hitl import ingest_decision
from spakky.plugins.agui.projector import AgUiProjector
from spakky.plugins.agui.transport import AgUiRunDriver


@Agent(
    spec=AgentExecutionSpec(
        name="hitl_assistant",
        objective="write after approval",
        accepted_signals=(
            AgentSignalKind.APPROVAL_DECISION,
            AgentSignalKind.CANCEL,
        ),
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
    )
)
class HitlAssistant:
    """Durable agent whose write tool requires human approval."""

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
        schema_name="note.write",
        description="Write a note after human approval.",
        effects=ToolEffects.write_state(),
        idempotency=Idempotency.CONDITIONALLY_IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.REQUIRED,
    )
    def note_write(self, topic: str) -> str:
        """Write a note for a topic after approval."""
        return f"write:{topic}"


class _ScriptedModel(IAgentModel):
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
            kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
            tool_call=ModelToolCall(
                name="note.write", arguments={"topic": "agents"}, call_id="write-1"
            ),
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


class _MemoryStateRepository(IAgentStateRepository):
    def __init__(self) -> None:
        self._states: dict[str, AgentState] = {}

    @override
    def get(self, state_id: str) -> AgentState:
        state = self._states.get(state_id)
        if state is None:
            raise AgentDefinitionError("Missing state")
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
        return tuple(s for s in self._states.values() if s.status is status)

    @override
    def list_resume_candidates(self) -> Sequence[AgentState]:
        return ()


class _MemorySignalRepository(IAgentSignalRepository):
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
            s
            for s in self._signals
            if s.agent_state_id == state_id and s.id not in self._consumed
        )

    @override
    def mark_consumed(self, signal_id: str) -> AgentSignal:
        for signal in self._signals:
            if signal.id == signal_id:
                self._consumed.add(signal_id)
                return signal
        raise AgentDefinitionError("Missing signal")

    def all_appended(self) -> tuple[AgentSignal, ...]:
        return self._signals


class _MemoryEvidenceRepository(IAgentEvidenceRepository):
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
            raise AgentDefinitionError("Missing evidence")
        return evidence

    @override
    def list_by_state(self, state_id: str) -> Sequence[AgentEvidence]:
        return tuple(a for a in self._evidence.values() if a.agent_state_id == state_id)

    @override
    def list_by_manifest_ref(self, manifest_ref: str) -> Sequence[AgentEvidence]:
        return ()


def _build_app(
    signals: _MemorySignalRepository,
) -> FastAPI:
    app = FastAPI()
    config = AgUiConfig()
    assistant = HitlAssistant(
        _ScriptedModel(), _MemoryStateRepository(), signals, _MemoryEvidenceRepository()
    )

    def run_driver_factory(
        core_input: RunAgentInput,
        ag_ui_input: AgUiRunAgentInput,
        accept: str | None,
    ) -> AgUiRunDriver:
        runner = AgentRunner.for_agent_instance(assistant)
        if core_input.resume:
            ingest_decision(ag_ui_input, signals, core_input.state_id)
        return AgUiRunDriver(
            runner=runner,
            run_input=core_input,
            agent_id="hitl_assistant",
            projector=AgUiProjector(config),
            encoder=EventEncoder(accept=accept or ""),
        )

    add_agui_endpoint(app, run_driver_factory=run_driver_factory, config=config)
    return app


def _initial_input() -> dict[str, object]:
    return {
        "threadId": "conv-1",
        "runId": "run-1",
        "state": None,
        "messages": [{"id": "u1", "role": "user", "content": "write a note"}],
        "tools": [],
        "context": [],
        "forwardedProps": None,
    }


def _resume_input(decision: str) -> dict[str, object]:
    return {
        "threadId": "conv-1",
        "runId": "run-1",
        "state": None,
        "messages": [
            {"id": "u1", "role": "user", "content": "write a note"},
            {
                "id": "t1",
                "role": "tool",
                "toolCallId": "approval:run-1:note.write",
                "content": (
                    '{"request_id": "approval:run-1:note.write",'
                    f' "decision": "{decision}"}}'
                ),
            },
        ],
        "tools": [],
        "context": [],
        "forwardedProps": None,
    }


def _types(text: str) -> list[str]:
    frames = [line for line in text.split("\n\n") if line.startswith("data: ")]
    return [loads(frame.removeprefix("data: ").strip())["type"] for frame in frames]


def test_hitl_run1_surfaces_deferred_approval_then_pauses() -> None:
    """run1이 hitl_approval deferred-tool 프레임을 스트리밍하고 결과 없이 멈춘다."""
    signals = _MemorySignalRepository()
    client = TestClient(_build_app(signals))

    response = client.post("/agui", json=_initial_input())
    text = response.text
    types = _types(text)

    assert "TOOL_CALL_START" in types
    assert "hitl_approval" in text
    # The approval has no result frame — it is deferred to the next input.
    assert "TOOL_CALL_RESULT" not in types


def test_hitl_resume_with_approve_writes_signal_and_streams_result() -> None:
    """run2 APPROVE가 signal을 적재하고 런너가 재개해 tool result+RUN_FINISHED를 흘린다."""
    signals = _MemorySignalRepository()
    client = TestClient(_build_app(signals))
    client.post("/agui", json=_initial_input())

    response = client.post("/agui", json=_resume_input("approve"))
    types = _types(response.text)

    approval_signals = [
        s for s in signals.all_appended() if s.kind is AgentSignalKind.APPROVAL_DECISION
    ]
    assert len(approval_signals) == 1
    assert approval_signals[0].payload["decision"] == "approve"
    assert "TOOL_CALL_RESULT" in types
    assert types[-1] == "RUN_FINISHED"


def test_hitl_resume_with_reject_terminates_without_tool_result() -> None:
    """run2 REJECT가 signal을 적재하고 도구 결과 없이 종단으로 끝난다."""
    signals = _MemorySignalRepository()
    client = TestClient(_build_app(signals))
    client.post("/agui", json=_initial_input())

    response = client.post("/agui", json=_resume_input("reject"))
    types = _types(response.text)

    approval_signals = [
        s for s in signals.all_appended() if s.kind is AgentSignalKind.APPROVAL_DECISION
    ]
    assert approval_signals[0].payload["decision"] == "reject"
    assert "TOOL_CALL_RESULT" not in types
    assert types[-1] == "RUN_ERROR"
