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
        """Claim unpublished messages for this relay instance (with lock).

        A partition key must be claimed whole: an implementation may only hand
        out messages of a key when it also claims that key's oldest message that
        is neither published nor abandoned. Otherwise two relay instances
        publish one key in parallel and lose the ordering the key exists to
        provide. Messages without a partition key carry no such constraint.
        """

    @abstractmethod
    def mark_published(self, message_id: UUID) -> None:
        """Mark a message as published."""

    @abstractmethod
    def increment_retry(self, message_id: UUID) -> None:
        """Increment the retry count of a message."""

    @abstractmethod
    def mark_abandoned(self, message_id: UUID) -> None:
        """Record that the relay gave up on a message after exhausting retries.

        The message leaves the pending queue without being published, so a
        partition key never waits forever on a message that will not be retried
        again. An implementation must keep the record and the reason readable —
        the operator has to be able to find what was dropped.
        """


class IAsyncOutboxStorage(ABC):
    """Asynchronous outbox message storage abstraction."""

    @abstractmethod
    async def save(self, message: OutboxMessage) -> None:
        """Save message within the current transaction."""

    @abstractmethod
    async def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
        """Claim unpublished messages for this relay instance (with lock).

        A partition key must be claimed whole: an implementation may only hand
        out messages of a key when it also claims that key's oldest message that
        is neither published nor abandoned. Otherwise two relay instances
        publish one key in parallel and lose the ordering the key exists to
        provide. Messages without a partition key carry no such constraint.
        """

    @abstractmethod
    async def mark_published(self, message_id: UUID) -> None:
        """Mark a message as published."""

    @abstractmethod
    async def increment_retry(self, message_id: UUID) -> None:
        """Increment the retry count of a message."""

    @abstractmethod
    async def mark_abandoned(self, message_id: UUID) -> None:
        """Record that the relay gave up on a message after exhausting retries.

        The message leaves the pending queue without being published, so a
        partition key never waits forever on a message that will not be retried
        again. An implementation must keep the record and the reason readable —
        the operator has to be able to find what was dropped.
        """
