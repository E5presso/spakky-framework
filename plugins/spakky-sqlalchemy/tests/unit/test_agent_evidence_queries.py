"""Unit tests for agent evidence queries and JSON column round trips."""

from collections.abc import Generator
from dataclasses import dataclass
from typing import cast

import pytest
from spakky.agent import (
    AgentEvidence,
    AgentEvidenceKind,
    AgentSignal,
    AgentSignalKind,
    AgentState,
    AgentStatus,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from spakky.plugins.sqlalchemy.agent.repository import (
    SqlAlchemyAgentEvidenceRepository,
    SqlAlchemyAgentSignalRepository,
    SqlAlchemyAgentStateRepository,
)
from spakky.plugins.sqlalchemy.agent.table import (
    AgentEvidenceTable,
    AgentStateTable,
)
from spakky.plugins.sqlalchemy.persistency.session_manager import SessionManager


@dataclass(slots=True)
class SessionManagerStub:
    """Minimal session manager shape used by repository unit tests."""

    session: Session


@pytest.fixture(name="session")
def session_fixture() -> Generator[Session, None, None]:
    """Create an isolated in-memory SQLAlchemy session."""
    engine = create_engine("sqlite:///:memory:")
    AgentStateTable.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_evidence_counts_steps_and_origins(session: Session) -> None:
    """Evidence count, step lookup and origin lookup use their own queries."""
    manager = cast(SessionManager, SessionManagerStub(session=session))
    evidence = SqlAlchemyAgentEvidenceRepository(manager)
    assert evidence.count_by_state("run") == 0
    stored = evidence.append(
        AgentEvidence(
            id="run:evidence:1",
            agent_state_id="run",
            kind=AgentEvidenceKind.CONTEXT_MANIFEST,
            payload={"model_step": 1},
            digest="fingerprint",
            model_step=1,
            origin_refs=("source:a", "source:b", "source:a"),
        )
    )
    assert stored.origin_refs == ("source:a", "source:b")
    evidence.append(
        AgentEvidence(
            id="run:evidence:2",
            agent_state_id="run",
            kind=AgentEvidenceKind.TOOL,
            payload={"result": {"ok": True}},
        )
    )
    assert evidence.count_by_state("run") == 2
    assert evidence.has_step_evidence(
        "run", AgentEvidenceKind.CONTEXT_MANIFEST, 1, "fingerprint"
    )
    assert not evidence.has_step_evidence(
        "run", AgentEvidenceKind.CONTEXT_MANIFEST, 2, "fingerprint"
    )
    found = evidence.list_by_origin_ref("source:b")
    assert [item.id for item in found] == ["run:evidence:1"]
    assert found[0].payload == {"model_step": 1}
    assert found[0].origin_refs == ("source:a", "source:b")
    assert evidence.list_by_origin_ref("source:none") == []
    assert evidence.get("run:evidence:2").payload == {"result": {"ok": True}}
    row = session.get(AgentEvidenceTable, "run:evidence:1")
    assert row is not None
    assert row.to_domain().payload == {"model_step": 1}
    assert row.to_domain().origin_refs == ()
    signals = SqlAlchemyAgentSignalRepository(manager)
    signals.append(
        AgentSignal(
            id="signal",
            agent_state_id="run",
            kind=AgentSignalKind.CANCEL,
            payload={"reason": "stop"},
        )
    )
    assert signals.list_pending("run")[0].payload == {"reason": "stop"}


def test_state_metadata_round_trips_in_its_json_column(session: Session) -> None:
    """Runner metadata keeps nested values and survives the state repository."""
    manager = cast(SessionManager, SessionManagerStub(session=session))
    states = SqlAlchemyAgentStateRepository(manager)
    metadata = {"runner_checkpoint": {"step": 2, "messages": [{"role": "user"}, None]}}
    states.save(
        AgentState(id="s", agent_type="t", status=AgentStatus.ACTIVE, metadata=metadata)
    )
    assert states.get("s").metadata == metadata
    assert states.list_by_status(AgentStatus.ACTIVE)[0].metadata == metadata
    assert states.list_resume_candidates()[0].metadata == metadata
