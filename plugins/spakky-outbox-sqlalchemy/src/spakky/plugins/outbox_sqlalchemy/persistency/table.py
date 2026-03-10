"""SQLAlchemy table definition for the Outbox pattern."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, LargeBinary, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class OutboxBase(DeclarativeBase):
    """Outbox-specific DeclarativeBase. Infrastructure table, not a domain model."""


class OutboxMessageTable(OutboxBase):
    """Outbox message table for transactional outbox pattern."""

    __tablename__ = "spakky_event_outbox"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    event_name: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
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
