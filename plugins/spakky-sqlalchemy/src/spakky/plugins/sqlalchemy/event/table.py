"""SQLAlchemy table recording which handler already processed which event."""

from datetime import datetime
from uuid import UUID

from spakky.plugins.sqlalchemy.orm.table import AbstractTable, Table
from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

SUBSCRIBER_COLUMN_LENGTH = 63
"""Matches the longest subscriber name the event contract accepts."""

HANDLER_COLUMN_LENGTH = 255
"""Upper bound of a handler name; longer names must be set explicitly shorter."""


@Table()
class ProcessedEventTable(AbstractTable):
    """Inbox table: one row per (subscriber, handler, event) processed.

    The composite primary key is what rejects a concurrent duplicate, so the
    table must be created with it. This is an infrastructure table that does
    not map to a domain model.
    """

    __tablename__ = "spakky_event_inbox"

    subscriber: Mapped[str] = mapped_column(
        String(SUBSCRIBER_COLUMN_LENGTH), primary_key=True
    )
    handler: Mapped[str] = mapped_column(
        String(HANDLER_COLUMN_LENGTH), primary_key=True
    )
    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_spakky_event_inbox_processed_at", "processed_at"),)
