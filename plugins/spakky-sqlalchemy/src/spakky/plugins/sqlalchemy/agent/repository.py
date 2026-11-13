"""SQLAlchemy repository implementations for spakky-agent contracts."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Final, override

from spakky.agent.evidence import AgentEvidence, AgentEvidenceKind
from spakky.agent.interfaces.repository import (
    IAgentEvidenceRepository,
    IAgentSignalRepository,
    IAgentStateRepository,
)
from spakky.agent.interfaces.task_store import ConversationTurn, ITaskStore
from spakky.agent.mailbox import IAgentSignalPublisher
from spakky.agent.signal import AgentSignal
from spakky.agent.state import AgentState, AgentStatus
from spakky.core.pod.annotations.pod import Pod
from spakky.core.utils.uuid import uuid7
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, SessionTransaction

from spakky.plugins.sqlalchemy.agent.error import (
    AgentConversationAppendConflictError,
    AgentPersistenceRowNotFoundError,
    AgentSignalTransactionMissingError,
)
from spakky.plugins.sqlalchemy.agent.table import (
    AgentConversationTurnTable,
    AgentEvidenceOriginTable,
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
        session = self._session_manager.session
        row = session.merge(AgentStateTable.from_domain(state))
        session.flush()
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
"""``Session.info`` key holding signals appended in still-open transactions."""


@dataclass(frozen=True, slots=True)
class _StagedSignal:
    """A ledger row awaiting its outermost transaction's commit."""

    transaction: SessionTransaction
    publisher: IAgentSignalPublisher
    signal: AgentSignal

    def belongs_to(self, ended: SessionTransaction) -> bool:
        """Return whether ``ended`` is this row's transaction or an ancestor."""
        current: SessionTransaction | None = self.transaction
        while current is not None:
            if current is ended:
                return True
            current = current.parent
        return False


@Pod()
class SqlAlchemyAgentSignalRepository(IAgentSignalRepository):
    """SQLAlchemy durable signal ledger that publishes rows after commit.

    ``append`` only stages the ledger row against the transaction (or
    savepoint) that wrote it. When a live publisher is wired, staged signals are
    published only when the outermost transaction commits. Rolling back a
    savepoint discards just the rows written inside it, and ending the outermost
    transaction without commit (rollback or ``close()``) discards the rest, so a
    running agent is never woken for a signal that did not durably commit.
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
        self._after_soft_rollback = self._discard_rolled_back
        self._after_transaction_end = self._discard_unfinished

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
        transaction = session.get_nested_transaction() or session.get_transaction()
        if transaction is None:  # pragma: no cover - flush() always begins one
            raise AgentSignalTransactionMissingError(signal.id)
        if not event.contains(session, "after_commit", self._after_commit):
            event.listen(session, "after_commit", self._after_commit)
            event.listen(session, "after_soft_rollback", self._after_soft_rollback)
            event.listen(session, "after_transaction_end", self._after_transaction_end)
        self._staged(session).append(_StagedSignal(transaction, publisher, signal))

    def _publish_committed(self, session: Session) -> None:
        # A released savepoint also emits after_commit; its rows wait for the
        # outermost commit and are still discarded if an outer level rolls back.
        if session.in_nested_transaction():
            return
        staged = session.info.pop(UNCOMMITTED_SIGNALS_KEY, [])
        for item in staged:
            item.publisher.publish(item.signal)

    def _discard_rolled_back(
        self, session: Session, previous_transaction: SessionTransaction
    ) -> None:
        staged = self._staged(session)
        staged[:] = [
            item for item in staged if not item.belongs_to(previous_transaction)
        ]

    def _discard_unfinished(
        self, session: Session, transaction: SessionTransaction
    ) -> None:
        if transaction.parent is None:
            session.info.pop(UNCOMMITTED_SIGNALS_KEY, None)

    @staticmethod
    def _staged(session: Session) -> list[_StagedSignal]:
        return session.info.setdefault(UNCOMMITTED_SIGNALS_KEY, [])


@Pod()
class SqlAlchemyAgentEvidenceRepository(IAgentEvidenceRepository):
    """SQLAlchemy append-only repository for agent evidence artifacts.

    Context origin references are indexed so a source erasure can find every run
    that read the source.
    """

    _session_manager: SessionManager

    def __init__(self, session_manager: SessionManager) -> None:
        self._session_manager = session_manager

    @override
    def append(self, evidence: AgentEvidence) -> AgentEvidence:
        session = self._session_manager.session
        row = AgentEvidenceTable.from_domain(evidence)
        session.add(row)
        origin_refs = tuple(dict.fromkeys(evidence.origin_refs))
        for position, origin_ref in enumerate(origin_refs):
            session.add(
                AgentEvidenceOriginTable(
                    evidence_id=evidence.id, origin_ref=origin_ref, position=position
                )
            )
        session.flush()
        return row.restore(origin_refs)

    @override
    def get(self, evidence_id: str) -> AgentEvidence:
        row = self._session_manager.session.get(AgentEvidenceTable, evidence_id)
        if row is None:
            raise AgentPersistenceRowNotFoundError(evidence_id)
        return self._restore((row,))[0]

    @override
    def list_by_state(self, state_id: str) -> Sequence[AgentEvidence]:
        rows = self._session_manager.session.scalars(
            select(AgentEvidenceTable)
            .where(AgentEvidenceTable.agent_state_id == state_id)
            .order_by(AgentEvidenceTable.created_at, AgentEvidenceTable.id)
        ).all()
        return self._restore(rows)

    @override
    def list_by_manifest_ref(self, manifest_ref: str) -> Sequence[AgentEvidence]:
        rows = self._session_manager.session.scalars(
            select(AgentEvidenceTable)
            .where(AgentEvidenceTable.manifest_ref == manifest_ref)
            .order_by(AgentEvidenceTable.created_at, AgentEvidenceTable.id)
        ).all()
        return self._restore(rows)

    @override
    def count_by_state(self, state_id: str) -> int:
        count = self._session_manager.session.scalar(
            select(func.count())
            .select_from(AgentEvidenceTable)
            .where(AgentEvidenceTable.agent_state_id == state_id)
        )
        return count or 0

    @override
    def has_step_evidence(
        self,
        state_id: str,
        kind: AgentEvidenceKind,
        model_step: int,
        digest: str,
    ) -> bool:
        found = self._session_manager.session.scalar(
            select(AgentEvidenceTable.id)
            .where(
                AgentEvidenceTable.agent_state_id == state_id,
                AgentEvidenceTable.kind == kind.value,
                AgentEvidenceTable.model_step == model_step,
                AgentEvidenceTable.digest == digest,
            )
            .limit(1)
        )
        return found is not None

    @override
    def list_by_origin_ref(self, origin_ref: str) -> Sequence[AgentEvidence]:
        rows = self._session_manager.session.scalars(
            select(AgentEvidenceTable)
            .join(
                AgentEvidenceOriginTable,
                AgentEvidenceOriginTable.evidence_id == AgentEvidenceTable.id,
            )
            .where(AgentEvidenceOriginTable.origin_ref == origin_ref)
            .order_by(AgentEvidenceTable.created_at, AgentEvidenceTable.id)
        ).all()
        return self._restore(rows)

    def _restore(self, rows: Sequence[AgentEvidenceTable]) -> list[AgentEvidence]:
        session = self._session_manager.session
        origins: dict[str, list[str]] = {}
        if rows:
            for origin in session.scalars(
                select(AgentEvidenceOriginTable)
                .where(
                    AgentEvidenceOriginTable.evidence_id.in_(
                        tuple(row.id for row in rows)
                    )
                )
                .order_by(AgentEvidenceOriginTable.position)
            ):
                origins.setdefault(origin.evidence_id, []).append(origin.origin_ref)
        return [row.restore(tuple(origins.get(row.id, ()))) for row in rows]


@Pod()
class SqlAlchemyAgentTaskStore(ITaskStore):
    """SQLAlchemy conversation-history store keyed by ``conversation_id``.

    Turns are appended after the last stored position of the conversation and
    read back in that order. When two writers append to one conversation at the
    same time, the unique ``(conversation_id, position)`` constraint lets only
    one of them succeed; the other fails with
    ``AgentConversationAppendConflictError`` instead of interleaving turns.
    """

    _session_manager: SessionManager

    def __init__(self, session_manager: SessionManager) -> None:
        self._session_manager = session_manager

    @override
    def load_history(self, conversation_id: str) -> Sequence[ConversationTurn]:
        rows = self._session_manager.session.scalars(
            select(AgentConversationTurnTable)
            .where(AgentConversationTurnTable.conversation_id == conversation_id)
            .order_by(AgentConversationTurnTable.position)
        ).all()
        return [row.to_turn() for row in rows]

    @override
    def append_turns(
        self,
        conversation_id: str,
        turns: Sequence[ConversationTurn],
    ) -> None:
        session = self._session_manager.session
        last_position = session.scalar(
            select(func.max(AgentConversationTurnTable.position)).where(
                AgentConversationTurnTable.conversation_id == conversation_id
            )
        )
        # None: the conversation has no stored turn yet.
        next_position = 0 if last_position is None else last_position + 1
        created_at = datetime.now(UTC)
        for offset, turn in enumerate(turns):
            session.add(
                AgentConversationTurnTable(
                    id=str(uuid7()),
                    conversation_id=conversation_id,
                    position=next_position + offset,
                    role=turn.role.value,
                    content=turn.content,
                    metadata_json=turn.metadata,
                    created_at=created_at,
                )
            )
        try:
            session.flush()
        except IntegrityError:
            raise AgentConversationAppendConflictError(conversation_id)
