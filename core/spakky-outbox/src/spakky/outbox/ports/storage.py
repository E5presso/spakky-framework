"""Outbox storage port."""

from abc import ABC, abstractmethod
from uuid import UUID

from spakky.outbox.common.message import OutboxMessage


class IOutboxStorage(ABC):
    """Synchronous outbox message storage abstraction."""

    @abstractmethod
    def save(self, message: OutboxMessage) -> None:
        """Save message within the current transaction."""

    @abstractmethod
    def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
        """Fetch unpublished messages (with lock)."""

    @abstractmethod
    def mark_published(self, message_id: UUID) -> None:
        """Mark a message as published."""

    @abstractmethod
    def increment_retry(self, message_id: UUID) -> None:
        """Increment the retry count of a message."""


class IAsyncOutboxStorage(ABC):
    """Asynchronous outbox message storage abstraction."""

    @abstractmethod
    async def save(self, message: OutboxMessage) -> None:
        """Save message within the current transaction."""

    @abstractmethod
    async def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
        """Fetch unpublished messages (with lock)."""

    @abstractmethod
    async def mark_published(self, message_id: UUID) -> None:
        """Mark a message as published."""

    @abstractmethod
    async def increment_retry(self, message_id: UUID) -> None:
        """Increment the retry count of a message."""
