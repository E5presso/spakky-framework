"""Outbox message model."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class OutboxMessage:
    """Persistence-agnostic Outbox message model."""

    id: UUID
    event_name: str
    payload: bytes
    headers: dict[str, str]
    created_at: datetime
    published_at: datetime | None = field(default=None)
    retry_count: int = field(default=0)
    claimed_at: datetime | None = field(default=None)
