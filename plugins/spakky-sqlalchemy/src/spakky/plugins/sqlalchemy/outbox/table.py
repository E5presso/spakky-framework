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
    # NULL carries the domain meaning "no key" — the broker spreads such
    # messages round-robin. Adding this column to an already-deployed table
    # still requires an explicit migration: see the schema upgrade section of
    # docs/guides/outbox.md.
    partition_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retry_count: Mapped[int] = mapped_column(default=0)
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set when the relay exhausted the retry budget without publishing. The row
    # then leaves the pending queue so its partition key stops waiting on it,
    # and stays readable for the operator. Adding this column to an
    # already-deployed table requires an explicit migration: see the schema
    # upgrade section of docs/guides/outbox.md.
    abandoned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_spakky_event_outbox_pending", "published_at", "created_at"),
    )
