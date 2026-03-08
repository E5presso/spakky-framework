from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, LargeBinary, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class OutboxBase(DeclarativeBase):
    """DeclarativeBase dedicated to the Outbox infrastructure table.

    Intentionally separate from the application SchemaRegistry so that the
    outbox table metadata is never mixed with domain model metadata.
    """


class OutboxMessageTable(OutboxBase):
    """Persistent store for outgoing integration events.

    Each row represents one integration event that must be delivered to the
    message broker. The Relay background service polls this table, delivers
    pending messages via IAsyncEventTransport, and marks them as published.
    """

    __tablename__ = "spakky_event_outbox"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    """Unique identifier for this outbox message."""

    event_name: Mapped[str] = mapped_column(String(255), nullable=False)
    """Topic / routing key — equals AbstractIntegrationEvent.event_name."""

    event_type: Mapped[str] = mapped_column(String(512), nullable=False)
    """Fully-qualified class name used by the Relay for deserialization."""

    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    """Pydantic-serialised JSON bytes of the integration event."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    """When the outbox message was persisted."""

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    """When the Relay successfully delivered the message (None = pending)."""

    retry_count: Mapped[int] = mapped_column(nullable=False, default=0)
    """How many delivery attempts have been made."""

    __table_args__ = (
        Index(
            "ix_spakky_event_outbox_pending",
            "published_at",
            "created_at",
        ),
    )
