"""Unit tests for SQLAlchemy-backed agent repositories."""

from dataclasses import dataclass
from datetime import datetime
from typing import cast, override
from collections.abc import Generator

import pytest
from spakky.agent import (
    AgentEvidence,
    AgentEvidenceKind,
    AgentSignal,
    AgentSignalKind,
    AgentSignalPriority,
    AgentState,
    AgentStatus,
    IAgentSignalPublisher,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from spakky.plugins.sqlalchemy.agent.error import AgentPersistenceRowNotFoundError
from spakky.plugins.sqlalchemy.agent.repository import (
    UNCOMMITTED_SIGNALS_KEY,
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


class RecordingPublisher(IAgentSignalPublisher):
    """Live publisher double recording every delivered signal."""

    def __init__(self) -> None:
        self.published: list[AgentSignal] = []

    @override
    def publish(self, signal: AgentSignal) -> None:
        self.published.append(signal)


def _urgent_signal(signal_id: str) -> AgentSignal:
    return AgentSignal(
        id=signal_id,
        agent_state_id="state-1",
        kind=AgentSignalKind.STEERING_INSTRUCTION,
        payload={"input_id": "a", "revision": 1, "content": "x", "final": True},
        created_at=datetime(2026, 5, 6, 1),
        priority=AgentSignalPriority.URGENT,
    )


def test_agent_signal_repository_commit_expect_publish_only_after_commit(
    session: Session, session_manager: SessionManager
) -> None:
    """append은 row만 staging하고 commit이 끝난 뒤에만 live publisher를 깨운다."""
    publisher = RecordingPublisher()
    repository = SqlAlchemyAgentSignalRepository(session_manager, publisher)

    stored = repository.append(_urgent_signal("signal-1"))

    assert stored.priority is AgentSignalPriority.URGENT
    assert publisher.published == []
    session.commit()
    assert [signal.id for signal in publisher.published] == ["signal-1"]
    assert publisher.published[0].priority is AgentSignalPriority.URGENT
    assert UNCOMMITTED_SIGNALS_KEY not in session.info


def test_agent_signal_repository_rollback_expect_never_published(
    session: Session, session_manager: SessionManager
) -> None:
    """rollback된 신호는 게시되지 않고 다음 commit에도 섞이지 않는다."""
    publisher = RecordingPublisher()
    repository = SqlAlchemyAgentSignalRepository(session_manager, publisher)

    repository.append(_urgent_signal("rolled-back"))
    session.rollback()
    repository.append(_urgent_signal("committed"))
    session.commit()
    session.commit()

    assert [signal.id for signal in publisher.published] == ["committed"]
    assert repository.list_pending("state-1") == [
        AgentSignal(
            id="committed",
            agent_state_id="state-1",
            kind=AgentSignalKind.STEERING_INSTRUCTION,
            payload={"input_id": "a", "revision": 1, "content": "x", "final": True},
            created_at=datetime(2026, 5, 6, 1),
        )
    ]


def test_agent_signal_repository_without_publisher_expect_ledger_only(
    session: Session, session_manager: SessionManager
) -> None:
    """publisher가 없으면 원장에만 기록하고 commit 대기 목록을 만들지 않는다."""
    repository = SqlAlchemyAgentSignalRepository(session_manager)

    repository.append(_urgent_signal("signal-1"))
    session.commit()

    assert UNCOMMITTED_SIGNALS_KEY not in session.info
    assert [signal.id for signal in repository.list_pending("state-1")] == ["signal-1"]


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
