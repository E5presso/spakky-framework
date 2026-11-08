"""Acceptance tests for SQLAlchemy agent persistence contribution."""

from asyncio import wait_for
from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Thread
from typing import cast

import pytest
from spakky.agent import (
    AgentEvidence,
    AgentEvidenceKind,
    AgentSignal,
    AgentSignalKind,
    AgentState,
    AgentStateReason,
    AgentStateTransition,
    AgentStatus,
    InProcessAgentSignalMailbox,
)
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

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
class _SessionManagerStub:
    session: Session


@pytest.fixture(name="engine")
def engine_fixture(tmp_path: Path) -> Generator[Engine, None, None]:
    """Create a file-backed SQLite database to model process restart."""
    engine = create_engine(f"sqlite:///{tmp_path / 'agent-acceptance.db'}")
    AgentStateTable.metadata.create_all(engine)
    AgentSignalTable.metadata.create_all(engine)
    AgentEvidenceTable.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def test_sqlalchemy_agent_contribution_acceptance_expect_restart_resume_state_signal_evidence(
    engine: Engine,
) -> None:
    """SQLAlchemy contribution이 restart 후 state/signal/evidence resume을 보존한다."""
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as first_session:
        states, signals, evidence = _repositories(first_session)
        state = AgentState(
            id="run-1",
            agent_type="CodeAssistant",
            status=AgentStatus.INTERRUPTED,
            transition=AgentStateTransition.WAITING_APPROVAL,
            reason=AgentStateReason.APPROVAL_REQUIRED,
            recovery_marker="boundary:workspace.write",
            metadata={"resume": "action_boundary"},
            created_at=datetime(2026, 5, 6, 1),
            updated_at=datetime(2026, 5, 6, 2),
        )
        signal = AgentSignal(
            id="signal-1",
            agent_state_id=state.id,
            kind=AgentSignalKind.APPROVAL_DECISION,
            payload={"decision": "approve", "request_id": "approval-1"},
            created_at=datetime(2026, 5, 6, 3),
        )
        boundary = AgentEvidence(
            id="evidence-1",
            agent_state_id=state.id,
            kind=AgentEvidenceKind.ACTION_BOUNDARY,
            payload={"action_id": "tool:workspace.write", "stage": "before"},
            summary="before workspace write",
            manifest_ref="manifest-1",
            created_at=datetime(2026, 5, 6, 4),
        )
        tool = AgentEvidence(
            id="evidence-2",
            agent_state_id=state.id,
            kind=AgentEvidenceKind.TOOL,
            payload={"tool": "workspace.write"},
            summary="workspace write completed",
            manifest_ref="manifest-1",
            created_at=datetime(2026, 5, 6, 5),
        )

        states.save(state)
        signals.append(signal)
        evidence.append(boundary)
        evidence.append(tool)
        first_session.commit()

    with session_factory() as restarted_session:
        states, signals, evidence = _repositories(restarted_session)

        assert states.get("run-1").recovery_marker == "boundary:workspace.write"
        assert states.list_resume_candidates() == [states.get("run-1")]
        assert signals.list_pending("run-1") == [
            AgentSignal(
                id="signal-1",
                agent_state_id="run-1",
                kind=AgentSignalKind.APPROVAL_DECISION,
                payload={"decision": "approve", "request_id": "approval-1"},
                created_at=datetime(2026, 5, 6, 3),
            )
        ]
        assert [artifact.id for artifact in evidence.list_by_state("run-1")] == [
            "evidence-1",
            "evidence-2",
        ]
        assert [
            artifact.id for artifact in evidence.list_by_manifest_ref("manifest-1")
        ] == [
            "evidence-1",
            "evidence-2",
        ]
        signals.mark_consumed("signal-1")
        restarted_session.commit()

    with session_factory() as resumed_session:
        states, signals, _ = _repositories(resumed_session)
        resumed = states.save(
            AgentState(
                id="run-1",
                agent_type="CodeAssistant",
                status=AgentStatus.ACTIVE,
                transition=AgentStateTransition.RUNNING,
                recovery_marker="boundary:workspace.write",
            )
        )
        resumed_session.commit()

        assert resumed.status is AgentStatus.ACTIVE
        assert signals.list_pending("run-1") == []
        assert states.list_resume_candidates() == [resumed]


async def test_sqlalchemy_signal_committed_on_producer_thread_expect_run_mailbox_woken(
    engine: Engine,
) -> None:
    """다른 스레드의 commit된 신호만 실행 메일박스를 깨우고, rollback은 깨우지 않는다."""
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    hub = InProcessAgentSignalMailbox()
    mailbox = hub.subscribe("run-1")

    def produce(signal_id: str, commit: bool) -> None:
        with session_factory() as producer_session:
            repository = SqlAlchemyAgentSignalRepository(
                cast(SessionManager, _SessionManagerStub(session=producer_session)),
                hub,
            )
            repository.append(
                AgentSignal(
                    id=signal_id,
                    agent_state_id="run-1",
                    kind=AgentSignalKind.CANCEL,
                    created_at=datetime(2026, 5, 6, 4),
                )
            )
            if commit:
                producer_session.commit()
            else:
                producer_session.rollback()

    rolled_back = Thread(target=produce, args=("rolled-back", False))
    rolled_back.start()
    rolled_back.join()
    assert mailbox.drain() == ()

    committed = Thread(target=produce, args=("committed", True))
    committed.start()
    await wait_for(mailbox.wait_control(), 1)
    committed.join()

    assert [signal.id for signal in mailbox.drain()] == ["committed"]
    with session_factory() as reader:
        _, signals, _ = _repositories(reader)
        assert [signal.id for signal in signals.list_pending("run-1")] == ["committed"]
    mailbox.close()


def _repositories(
    session: Session,
) -> tuple[
    SqlAlchemyAgentStateRepository,
    SqlAlchemyAgentSignalRepository,
    SqlAlchemyAgentEvidenceRepository,
]:
    session_manager = cast(SessionManager, _SessionManagerStub(session=session))
    return (
        SqlAlchemyAgentStateRepository(session_manager),
        SqlAlchemyAgentSignalRepository(session_manager),
        SqlAlchemyAgentEvidenceRepository(session_manager),
    )
