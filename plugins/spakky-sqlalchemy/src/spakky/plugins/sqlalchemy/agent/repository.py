"""SQLAlchemy repository implementations for spakky-agent contracts."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import override

from spakky.agent.evidence import AgentEvidence
from spakky.agent.interfaces.repository import (
    IAgentEvidenceRepository,
    IAgentSignalRepository,
    IAgentStateRepository,
)
from spakky.agent.signal import AgentSignal
from spakky.agent.state import AgentState, AgentStatus
from spakky.core.pod.annotations.pod import Pod
from sqlalchemy import select

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


@Pod()
class SqlAlchemyAgentSignalRepository(IAgentSignalRepository):
    """SQLAlchemy durable inbound queue repository for agent signals."""

    _session_manager: SessionManager

    def __init__(self, session_manager: SessionManager) -> None:
        self._session_manager = session_manager

    @override
    def append(self, signal: AgentSignal) -> AgentSignal:
        row = AgentSignalTable.from_domain(signal)
        self._session_manager.session.add(row)
        self._session_manager.session.flush()
        return row.to_domain()

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
