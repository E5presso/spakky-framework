"""SQLAlchemy repository implementations for spakky-agent contracts."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Final, override

from spakky.agent.evidence import AgentEvidence
from spakky.agent.interfaces.repository import (
    IAgentEvidenceRepository,
    IAgentSignalRepository,
    IAgentStateRepository,
)
from spakky.agent.mailbox import IAgentSignalPublisher
from spakky.agent.signal import AgentSignal
from spakky.agent.state import AgentState, AgentStatus
from spakky.core.pod.annotations.pod import Pod
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from spakky.plugins.sqlalchemy.agent.error import AgentPersistenceRowNotFoundError
from spakky.plugins.sqlalchemy.agent.table import (
    AgentEvidenceTable,
    AgentSignalTable,
    AgentStateTable,
)
from spakky.plugins.sqlalchemy.persistency.session_manager import SessionManager


@Pod()
class SqlAlchemyAgentStateRepository(IAgentStateRepository):
    """SQLAlchemy materialized state repository for agent executions."""

    _session_manager: SessionManager

    def __init__(self, session_manager: SessionManager) -> None:
        self._session_manager = session_manager

    @override
    def get(self, state_id: str) -> AgentState:
        state = self.get_or_none(state_id)
        if state is None:
            raise AgentPersistenceRowNotFoundError(state_id)
        return state

    @override
    def get_or_none(self, state_id: str) -> AgentState | None:
        row = self._session_manager.session.get(AgentStateTable, state_id)
        return row.to_domain() if row else None

    @override
    def save(self, state: AgentState) -> AgentState:
        row = self._session_manager.session.merge(AgentStateTable.from_domain(state))
        self._session_manager.session.flush()
        return row.to_domain()

    @override
    def list_by_status(self, status: AgentStatus) -> Sequence[AgentState]:
        rows = self._session_manager.session.scalars(
            select(AgentStateTable)
            .where(AgentStateTable.status == status.value)
            .order_by(AgentStateTable.updated_at, AgentStateTable.id)
        ).all()
        return [row.to_domain() for row in rows]

    @override
    def list_resume_candidates(self) -> Sequence[AgentState]:
        rows = self._session_manager.session.scalars(
            select(AgentStateTable)
            .where(
                AgentStateTable.status.in_(
                    (AgentStatus.ACTIVE.value, AgentStatus.INTERRUPTED.value)
                )
            )
            .order_by(AgentStateTable.updated_at, AgentStateTable.id)
        ).all()
        return [row.to_domain() for row in rows]


UNCOMMITTED_SIGNALS_KEY: Final = "spakky.agent.uncommitted_signals"
"""``Session.info`` key holding signals appended in the open transaction."""


@Pod()
class SqlAlchemyAgentSignalRepository(IAgentSignalRepository):
    """SQLAlchemy durable signal ledger that publishes rows after commit.

    ``append`` only stages the ledger row. When a live publisher is wired, the
    staged signals are published from the session's ``after_commit`` event and
    discarded on ``after_rollback``, so a running agent is never woken for a
    signal that did not durably commit.
    """

    _session_manager: SessionManager
    # publisher is None when no live mailbox is wired; rows are then replayed
    # only when a run starts or resumes.
    _publisher: IAgentSignalPublisher | None

    def __init__(
        self,
        session_manager: SessionManager,
        publisher: IAgentSignalPublisher | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._publisher = publisher
        # Bound once so SQLAlchemy can recognize an already registered listener.
        self._after_commit = self._publish_committed
        self._after_rollback = self._discard_uncommitted

    @override
    def append(self, signal: AgentSignal) -> AgentSignal:
        session = self._session_manager.session
        row = AgentSignalTable.from_domain(signal)
        session.add(row)
        session.flush()
        stored = replace(row.to_domain(), priority=signal.priority)
        if self._publisher is not None:
            self._stage_for_commit(session, self._publisher, stored)
        return stored

    @override
    def list_pending(self, state_id: str) -> Sequence[AgentSignal]:
        rows = self._session_manager.session.scalars(
            select(AgentSignalTable)
            .where(AgentSignalTable.agent_state_id == state_id)
            .where(AgentSignalTable.consumed_at.is_(None))
            .order_by(AgentSignalTable.created_at, AgentSignalTable.id)
        ).all()
        return [row.to_domain() for row in rows]

    @override
    def mark_consumed(self, signal_id: str) -> AgentSignal:
        row = self._session_manager.session.get(AgentSignalTable, signal_id)
        if row is None:
            raise AgentPersistenceRowNotFoundError(signal_id)
        row.consumed_at = datetime.now(UTC)
        self._session_manager.session.flush()
        return row.to_domain()

    def _stage_for_commit(
        self,
        session: Session,
        publisher: IAgentSignalPublisher,
        signal: AgentSignal,
    ) -> None:
        if not event.contains(session, "after_commit", self._after_commit):
            event.listen(session, "after_commit", self._after_commit)
            event.listen(session, "after_rollback", self._after_rollback)
        staged: list[tuple[IAgentSignalPublisher, AgentSignal]] = (
            session.info.setdefault(UNCOMMITTED_SIGNALS_KEY, [])
        )
        staged.append((publisher, signal))

    def _publish_committed(self, session: Session) -> None:
        staged: list[tuple[IAgentSignalPublisher, AgentSignal]] = session.info.pop(
            UNCOMMITTED_SIGNALS_KEY, []
        )
        for publisher, signal in staged:
            publisher.publish(signal)

    def _discard_uncommitted(self, session: Session) -> None:
        session.info.pop(UNCOMMITTED_SIGNALS_KEY, None)


@Pod()
class SqlAlchemyAgentEvidenceRepository(IAgentEvidenceRepository):
    """SQLAlchemy append-only repository for agent evidence artifacts."""

    _session_manager: SessionManager

    def __init__(self, session_manager: SessionManager) -> None:
        self._session_manager = session_manager

    @override
    def append(self, evidence: AgentEvidence) -> AgentEvidence:
        row = AgentEvidenceTable.from_domain(evidence)
        self._session_manager.session.add(row)
        self._session_manager.session.flush()
        return row.to_domain()

    @override
    def get(self, evidence_id: str) -> AgentEvidence:
        row = self._session_manager.session.get(AgentEvidenceTable, evidence_id)
        if row is None:
            raise AgentPersistenceRowNotFoundError(evidence_id)
        return row.to_domain()

    @override
    def list_by_state(self, state_id: str) -> Sequence[AgentEvidence]:
        rows = self._session_manager.session.scalars(
            select(AgentEvidenceTable)
            .where(AgentEvidenceTable.agent_state_id == state_id)
            .order_by(AgentEvidenceTable.created_at, AgentEvidenceTable.id)
        ).all()
        return [row.to_domain() for row in rows]

    @override
    def list_by_manifest_ref(self, manifest_ref: str) -> Sequence[AgentEvidence]:
        rows = self._session_manager.session.scalars(
            select(AgentEvidenceTable)
            .where(AgentEvidenceTable.manifest_ref == manifest_ref)
            .order_by(AgentEvidenceTable.created_at, AgentEvidenceTable.id)
        ).all()
        return [row.to_domain() for row in rows]
