"""SQLAlchemy table definition for the Outbox pattern."""

from datetime import datetime
from uuid import UUID

from spakky.plugins.sqlalchemy.orm.table import AbstractTable, Table
from sqlalchemy import JSON, DateTime, Index, LargeBinary, Text
from sqlalchemy.orm import Mapped, mapped_column


@Table()
class OutboxMessageTable(AbstractTable):
    """Outbox message table for transactional outbox pattern.

    This is an infrastructure table that doesn't map to a domain model,
    so it inherits from AbstractTable (not AbstractMappableTable).
    """

    __tablename__ = "spakky_event_outbox"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    event_name: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    headers: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retry_count: Mapped[int] = mapped_column(default=0)
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_spakky_event_outbox_pending", "published_at", "created_at"),
    )
