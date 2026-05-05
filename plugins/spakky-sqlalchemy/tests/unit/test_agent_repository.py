"""Unit tests for SQLAlchemy-backed agent repositories."""

from dataclasses import dataclass
from datetime import datetime
from typing import Generator, cast

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

from spakky.plugins.sqlalchemy.agent.error import AgentPersistenceRowNotFoundError
from spakky.plugins.sqlalchemy.agent.repository import (
    SqlAlchemyAgentEvidenceRepository,
    SqlAlchemyAgentSignalRepository,
    SqlAlchemyAgentStateRepository,
)
from spakky.plugins.sqlalchemy.agent.table import (
    AgentEvidenceTable,
    AgentSignalTable,
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
    AgentSignalTable.metadata.create_all(engine)
    AgentEvidenceTable.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(name="session_manager")
def session_manager_fixture(session: Session) -> SessionManager:
    """Return a typed session manager stub for repository construction."""
    return cast(SessionManager, SessionManagerStub(session=session))


def test_agent_state_repository_expect_save_get_and_resume_queries(
    session_manager: SessionManager,
) -> None:
    """state repository가 저장, 상태 조회, resume 후보 조회를 지원한다."""
    repository = SqlAlchemyAgentStateRepository(session_manager)
    active_state = AgentState(
        id="state-1",
        agent_type="CodeAssistant",
        status=AgentStatus.ACTIVE,
        current_activity="thinking",
        metadata={"task": "inspect"},
        created_at=datetime(2026, 5, 6),
        updated_at=datetime(2026, 5, 6),
    )
    completed_state = AgentState(
        id="state-2",
        agent_type="CodeAssistant",
        status=AgentStatus.COMPLETED,
        updated_at=datetime(2026, 5, 7),
    )

    saved = repository.save(active_state)
    repository.save(completed_state)

    assert saved == active_state
    assert repository.get("state-1") == active_state
    assert repository.get_or_none("missing") is None
    assert repository.list_by_status(AgentStatus.ACTIVE) == [active_state]
    assert repository.list_resume_candidates() == [active_state]


def test_agent_state_repository_get_missing_expect_custom_error(
    session_manager: SessionManager,
) -> None:
    """없는 state 조회는 plugin custom error로 실패한다."""
    repository = SqlAlchemyAgentStateRepository(session_manager)

    with pytest.raises(AgentPersistenceRowNotFoundError):
        repository.get("missing")


def test_agent_signal_repository_expect_append_pending_and_mark_consumed(
    session_manager: SessionManager,
) -> None:
    """signal repository가 pending queue와 consumed marker를 관리한다."""
    repository = SqlAlchemyAgentSignalRepository(session_manager)
    first_signal = AgentSignal(
        id="signal-1",
        agent_state_id="state-1",
        kind=AgentSignalKind.USER_MESSAGE,
        payload={"message": "continue"},
        created_at=datetime(2026, 5, 6, 1),
    )
    second_signal = AgentSignal(
        id="signal-2",
        agent_state_id="state-1",
        kind=AgentSignalKind.CANCEL,
        created_at=datetime(2026, 5, 6, 2),
    )

    assert repository.append(first_signal) == first_signal
    assert repository.append(second_signal) == second_signal
    assert repository.list_pending("state-1") == [first_signal, second_signal]

    consumed = repository.mark_consumed("signal-1")

    assert consumed == first_signal
    assert repository.list_pending("state-1") == [second_signal]


def test_agent_signal_repository_mark_missing_expect_custom_error(
    session_manager: SessionManager,
) -> None:
    """없는 signal consume은 plugin custom error로 실패한다."""
    repository = SqlAlchemyAgentSignalRepository(session_manager)

    with pytest.raises(AgentPersistenceRowNotFoundError):
        repository.mark_consumed("missing")


def test_agent_evidence_repository_expect_append_get_and_filter_queries(
    session_manager: SessionManager,
) -> None:
    """evidence repository가 append/read 전용 조회를 지원한다."""
    repository = SqlAlchemyAgentEvidenceRepository(session_manager)
    manifest_evidence = AgentEvidence(
        id="evidence-1",
        agent_state_id="state-1",
        kind=AgentEvidenceKind.CONTEXT_MANIFEST,
        payload={"path": "manifest.json"},
        manifest_ref="manifest-1",
        created_at=datetime(2026, 5, 6, 1),
    )
    tool_evidence = AgentEvidence(
        id="evidence-2",
        agent_state_id="state-1",
        kind=AgentEvidenceKind.TOOL,
        summary="read file",
        created_at=datetime(2026, 5, 6, 2),
    )

    assert repository.append(manifest_evidence) == manifest_evidence
    assert repository.append(tool_evidence) == tool_evidence
    assert repository.get("evidence-1") == manifest_evidence
    assert repository.list_by_state("state-1") == [manifest_evidence, tool_evidence]
    assert repository.list_by_manifest_ref("manifest-1") == [manifest_evidence]


def test_agent_evidence_repository_get_missing_expect_custom_error(
    session_manager: SessionManager,
) -> None:
    """없는 evidence 조회는 plugin custom error로 실패한다."""
    repository = SqlAlchemyAgentEvidenceRepository(session_manager)

    with pytest.raises(AgentPersistenceRowNotFoundError):
        repository.get("missing")
