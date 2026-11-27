"""Acceptance tests for the evidence order of a run stored through SQLAlchemy."""

from collections.abc import AsyncIterator, Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast, override

import pytest
from spakky.agent import (
    Agent,
    AgentEvidence,
    AgentEvidenceKind,
    AgentExecutionSpec,
    AgentRunner,
    AgentSignalKind,
    AgentYieldKind,
    EvidenceCapture,
    IAgentModel,
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
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from spakky.plugins.sqlalchemy.agent.repository import (
    SqlAlchemyAgentEvidenceRepository,
    SqlAlchemyAgentSignalRepository,
    SqlAlchemyAgentStateRepository,
)
from spakky.plugins.sqlalchemy.agent.table import (
    AgentEvidenceOriginTable,
    AgentEvidenceTable,
    AgentSignalTable,
    AgentStateTable,
)
from spakky.plugins.sqlalchemy.persistency.session_manager import SessionManager

TOOL_STEPS = 3
"""Model steps that call a tool; enough for the run to pass ten evidence rows."""

TWO_DIGIT_EVIDENCE_COUNT = 10
"""First evidence count whose id sorts before a one-digit id as text."""


@dataclass(slots=True)
class _SessionManagerStub:
    session: Session


@dataclass(frozen=True, slots=True)
class _Lookup:
    value: str


class _ToolLoopModel(IAgentModel):
    """Calls the lookup tool on the first ``TOOL_STEPS`` steps, then answers."""

    def __init__(self) -> None:
        self.steps = 0

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability(supports_tools=True)

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="answer")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        self.steps += 1
        if self.steps <= TOOL_STEPS:
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
                tool_call=ModelToolCall(
                    name="catalog.lookup",
                    arguments={"value": f"item-{self.steps}"},
                    call_id=f"call-{self.steps}",
                ),
            )
        else:
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.MESSAGE_DELTA, message_delta="answer"
            )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


@Agent(
    spec=AgentExecutionSpec(
        name="evidence_order_probe",
        accepted_signals=(AgentSignalKind.CANCEL,),
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
    )
)
class _DurableAgent:
    def __init__(
        self,
        model: IAgentModel,
        states: SqlAlchemyAgentStateRepository,
        signals: SqlAlchemyAgentSignalRepository,
        evidence: SqlAlchemyAgentEvidenceRepository,
    ) -> None:
        self._model = model
        self._states = states
        self._signals = signals
        self._evidence = evidence

    @agent_tool(
        schema_name="catalog.lookup",
        description="Look up one catalog item.",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def lookup(self, value: str) -> _Lookup:
        """Return the looked-up item."""
        return _Lookup(value=value)


@pytest.fixture(name="engine")
def engine_fixture(tmp_path: Path) -> Generator[Engine, None, None]:
    """File-backed SQLite database holding the agent tables."""
    engine = create_engine(f"sqlite:///{tmp_path / 'agent-evidence-order.db'}")
    for table in (
        AgentStateTable,
        AgentSignalTable,
        AgentEvidenceTable,
        AgentEvidenceOriginTable,
    ):
        table.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def _evidence_number(evidence: AgentEvidence) -> int:
    return int(evidence.id.rsplit(":", 1)[1])


@pytest.mark.asyncio
async def test_agent_runner_sqlalchemy_evidence_more_than_ten_expect_read_in_append_order(
    engine: Engine,
) -> None:
    """실행기가 넣은 증거가 열 개를 넘어도 넣은 순서로 다시 읽힌다."""
    with Session(engine, expire_on_commit=False) as session:
        manager = cast(SessionManager, _SessionManagerStub(session))
        evidence = SqlAlchemyAgentEvidenceRepository(manager)
        runner = AgentRunner.for_agent_instance(
            _DurableAgent(
                _ToolLoopModel(),
                SqlAlchemyAgentStateRepository(manager),
                SqlAlchemyAgentSignalRepository(manager),
                evidence,
            )
        )

        items = [
            item
            async for item in runner.run(
                RunAgentInput(state_id="run-1", instruction="go")
            )
        ]
        session.commit()
        stored = evidence.list_by_state("run-1")

    assert items[-1].kind is AgentYieldKind.FINAL
    numbers = [_evidence_number(item) for item in stored]
    assert len(numbers) > TWO_DIGIT_EVIDENCE_COUNT
    assert numbers == list(range(1, len(numbers) + 1))
    created = [item.created_at for item in stored if item.created_at is not None]
    assert len(created) == len(stored)
    assert created == sorted(created)
    assert len(set(created)) == len(created)


def test_sqlalchemy_agent_evidence_equal_or_missing_timestamps_expect_numbered_order(
    engine: Engine,
) -> None:
    """시각이 없거나 같은 증거도 번호 순서로 읽히고, 시각 없는 옛 행이 먼저 온다."""
    moment = datetime(2026, 11, 27, tzinfo=UTC)
    with Session(engine) as session:
        evidence = SqlAlchemyAgentEvidenceRepository(
            cast(SessionManager, _SessionManagerStub(session))
        )
        for number, created_at in (
            (12, moment),
            (11, moment),
            (2, None),
            (10, None),
            (1, None),
        ):
            evidence.append(
                AgentEvidence(
                    id=f"run-1:evidence:{number}",
                    agent_state_id="run-1",
                    kind=AgentEvidenceKind.MODEL,
                    manifest_ref="manifest-1",
                    created_at=created_at,
                )
            )
        session.commit()

        by_state = [_evidence_number(item) for item in evidence.list_by_state("run-1")]
        by_manifest = [
            _evidence_number(item)
            for item in evidence.list_by_manifest_ref("manifest-1")
        ]

    assert by_state == [1, 2, 10, 11, 12]
    assert by_manifest == [1, 2, 10, 11, 12]
