"""Outbox storage port."""

from abc import ABC, abstractmethod
from datetime import datetime
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

    @abstractmethod
    def release_claim(self, message: OutboxMessage) -> None:
        """Give up this relay's claim on a message it did not publish.

        Called when sending the message failed, so the next read can hand it
        out again instead of waiting for `claim_timeout_seconds` to expire.
        Only the claim is cleared: the retry count, a published message and an
        abandoned message stay as they are.

        The claim is released only while it is still the one `fetch_pending`
        handed out, identified by `message.claimed_at`. A relay that stalled
        past `claim_timeout_seconds` may find the message claimed again by
        another instance; clearing that newer claim would let a third read
        send it in parallel and break the partition key ordering.

        Args:
            message: The message as returned by `fetch_pending`.
        """

    @abstractmethod
    def purge_published(self, older_than: datetime) -> int:
        """Delete messages published before `older_than` and return how many.

        Only published messages are removed. A message still awaiting delivery
        and a message the relay abandoned both stay, whatever their age: the
        first is still owed to the broker and the second is the operator's
        record of what was dropped.

        Args:
            older_than: Messages whose `published_at` is earlier than this are
                deleted. Use a timezone-aware datetime.

        Returns:
            Number of deleted messages.
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

    @abstractmethod
    async def release_claim(self, message: OutboxMessage) -> None:
        """Give up this relay's claim on a message it did not publish.

        Called when sending the message failed, so the next read can hand it
        out again instead of waiting for `claim_timeout_seconds` to expire.
        Only the claim is cleared: the retry count, a published message and an
        abandoned message stay as they are.

        The claim is released only while it is still the one `fetch_pending`
        handed out, identified by `message.claimed_at`. A relay that stalled
        past `claim_timeout_seconds` may find the message claimed again by
        another instance; clearing that newer claim would let a third read
        send it in parallel and break the partition key ordering.

        Args:
            message: The message as returned by `fetch_pending`.
        """

    @abstractmethod
    async def purge_published(self, older_than: datetime) -> int:
        """Delete messages published before `older_than` and return how many.

        Only published messages are removed. A message still awaiting delivery
        and a message the relay abandoned both stay, whatever their age: the
        first is still owed to the broker and the second is the operator's
        record of what was dropped.

        Args:
            older_than: Messages whose `published_at` is earlier than this are
                deleted. Use a timezone-aware datetime.

        Returns:
            Number of deleted messages.
        """
