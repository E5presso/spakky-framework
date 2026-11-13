"""Idempotent consumption contract for integration event handlers.

Brokers deliver at least once, so a handler can see the same event again after
a crash, a rebalance or a retry. `@Idempotent()` makes a handler skip an event
it has already processed. The record is keyed by subscriber, handler and event
id, and is written through the handler's own transaction, so the record and the
handler's changes commit or roll back together.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from spakky.core.common.annotation import FunctionAnnotation

from spakky.event.error import AbstractSpakkyEventError
from spakky.event.subscription import HandlerName, SubscriberName


class ProcessedEventKey(BaseModel):
    """Identity of one handler having processed one event."""

    model_config = ConfigDict(frozen=True)

    subscriber: SubscriberName
    """Subscriber key; the unnamed subscriber is the empty string."""

    handler: HandlerName
    event_id: UUID


class ProcessedEventStoreUnavailableError(AbstractSpakkyEventError):
    """Raised when an idempotent handler runs without a processed-event store."""

    message = "Idempotent event handling requires a processed-event store provider"


class IProcessedEventStore(ABC):
    """Synchronous store of processed-event records.

    `record` must write through the transaction that is active for the calling
    handler and must fail when none is active; a record committed apart from
    the handler's changes would either lose the event or process it twice.
    """

    @abstractmethod
    def exists(self, key: ProcessedEventKey) -> bool:
        """Return whether the handler already processed the event."""
        ...

    @abstractmethod
    def record(self, key: ProcessedEventKey) -> None:
        """Record the event as processed inside the caller's transaction.

        A concurrent duplicate must fail here or at commit, never be accepted
        twice.
        """
        ...

    @abstractmethod
    def purge(self, older_than: datetime) -> int:
        """Delete records processed before `older_than`.

        Returns:
            Number of records removed.
        """
        ...


class IAsyncProcessedEventStore(ABC):
    """Asynchronous store of processed-event records.

    Follows the same contract as `IProcessedEventStore`.
    """

    @abstractmethod
    async def exists(self, key: ProcessedEventKey) -> bool:
        """Return whether the handler already processed the event."""
        ...

    @abstractmethod
    async def record(self, key: ProcessedEventKey) -> None:
        """Record the event as processed inside the caller's transaction.

        A concurrent duplicate must fail here or at commit, never be accepted
        twice.
        """
        ...

    @abstractmethod
    async def purge(self, older_than: datetime) -> int:
        """Delete records processed before `older_than`.

        Returns:
            Number of records removed.
        """
        ...


@dataclass
class Idempotent(FunctionAnnotation):
    """Marks an integration event handler as processing each event once.

    Combine it with `@Transactional()` so the processed record and the
    handler's changes share one transaction:

        @EventHandler(subscriber="billing")
        class BillingHandler:
            @on_event(OrderPlaced)
            @Transactional()
            @Idempotent()
            async def charge(self, event: OrderPlaced) -> None: ...
    """

    ...


def idempotent[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Decorator form of `Idempotent()`.

    Args:
        func: Event handler method to mark.

    Returns:
        The same method carrying the idempotency annotation.
    """
    return Idempotent()(func)
