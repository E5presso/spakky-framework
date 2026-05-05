"""SQLAlchemy schema mappings for spakky-agent persistence contracts."""

from datetime import datetime
from typing import Self, cast

from spakky.agent.evidence import AgentEvidence, AgentEvidenceKind
from spakky.agent.execution import AgentSignalKind
from spakky.agent.signal import AgentSignal
from spakky.agent.state import (
    AgentState,
    AgentStateReason,
    AgentStateTransition,
    AgentStatus,
)
from spakky.agent.types import JsonObject
from sqlalchemy import JSON, DateTime, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from spakky.plugins.sqlalchemy.orm.table import AbstractMappableTable, Table


@Table()
class AgentStateTable(AbstractMappableTable[AgentState]):
    """Materialized state table for durable agent executions."""

    __tablename__ = "spakky_agent_state"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    agent_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    transition: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_activity: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_signal_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    last_event_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    recovery_marker: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[JsonObject] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_spakky_agent_state_status", "status"),
        Index("ix_spakky_agent_state_resume", "status", "updated_at"),
    )

    @classmethod
    def from_domain(cls, domain: AgentState) -> Self:
        return cls(
            id=domain.id,
            agent_type=domain.agent_type,
            status=domain.status.value,
            transition=domain.transition.value if domain.transition else None,
            reason=domain.reason.value if domain.reason else None,
            current_activity=domain.current_activity,
            input_ref=domain.input_ref,
            output_ref=domain.output_ref,
            pending_signal_count=domain.pending_signal_count,
            last_event_cursor=domain.last_event_cursor,
            recovery_marker=domain.recovery_marker,
            metadata_json=domain.metadata,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
        )

    def to_domain(self) -> AgentState:
        return AgentState(
            id=self.id,
            agent_type=self.agent_type,
            status=AgentStatus(self.status),
            transition=(
                AgentStateTransition(self.transition) if self.transition else None
            ),
            reason=AgentStateReason(self.reason) if self.reason else None,
            current_activity=self.current_activity,
            input_ref=self.input_ref,
            output_ref=self.output_ref,
            pending_signal_count=self.pending_signal_count,
            last_event_cursor=self.last_event_cursor,
            recovery_marker=self.recovery_marker,
            metadata=cast(JsonObject, self.metadata_json),
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


@Table()
class AgentSignalTable(AbstractMappableTable[AgentSignal]):
    """Durable inbound signal queue table for agent executions."""

    __tablename__ = "spakky_agent_signal"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    agent_state_id: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[JsonObject] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "ix_spakky_agent_signal_pending",
            "agent_state_id",
            "consumed_at",
            "created_at",
        ),
    )

    @classmethod
    def from_domain(cls, domain: AgentSignal) -> Self:
        return cls(
            id=domain.id,
            agent_state_id=domain.agent_state_id,
            kind=domain.kind.value,
            payload=domain.payload,
            created_at=domain.created_at,
        )

    def to_domain(self) -> AgentSignal:
        return AgentSignal(
            id=self.id,
            agent_state_id=self.agent_state_id,
            kind=AgentSignalKind(self.kind),
            payload=cast(JsonObject, self.payload),
            created_at=self.created_at,
        )


@Table()
class AgentEvidenceTable(AbstractMappableTable[AgentEvidence]):
    """Append-only evidence table for agent execution artifacts."""

    __tablename__ = "spakky_agent_evidence"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    agent_state_id: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[JsonObject] = mapped_column(JSON, nullable=False, default=dict)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_spakky_agent_evidence_state", "agent_state_id", "created_at"),
        Index("ix_spakky_agent_evidence_manifest", "manifest_ref", "created_at"),
    )

    @classmethod
    def from_domain(cls, domain: AgentEvidence) -> Self:
        return cls(
            id=domain.id,
            agent_state_id=domain.agent_state_id,
            kind=domain.kind.value,
            payload=domain.payload,
            summary=domain.summary,
            digest=domain.digest,
            manifest_ref=domain.manifest_ref,
            reference=domain.reference,
            created_at=domain.created_at,
        )

    def to_domain(self) -> AgentEvidence:
        return AgentEvidence(
            id=self.id,
            agent_state_id=self.agent_state_id,
            kind=AgentEvidenceKind(self.kind),
            payload=cast(JsonObject, self.payload),
            summary=self.summary,
            digest=self.digest,
            manifest_ref=self.manifest_ref,
            reference=self.reference,
            created_at=self.created_at,
        )
