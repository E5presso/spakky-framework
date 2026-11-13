"""In-memory broker that fans published events out to subscriber queues."""

from collections import deque
from collections.abc import Awaitable, Callable
from asyncio import sleep as async_sleep
from threading import RLock
from time import sleep

from pydantic import BaseModel, ConfigDict
from spakky.core.pod.annotations.pod import Pod

from spakky.event.delivery import DeadLetter, DeliveryState
from spakky.event.subscription import SubscriberName

IN_FLIGHT_POLL_INTERVAL = 0.001
"""Seconds `drain` waits between checks on a message another consumer is handling."""

type SubscriptionKey = tuple[str, SubscriberName | None]
"""Event name and subscriber identifying one in-memory queue."""


class InMemoryMessage(BaseModel):
    """One published event as a subscriber queue holds it."""

    model_config = ConfigDict(frozen=True)

    event_name: str
    payload: bytes
    headers: dict[str, str]
    partition_key: str | None = None
    """Recorded for assertions; in-memory queues are not partitioned."""

    state: DeliveryState = DeliveryState()
    """Retry state of this message for the subscriber owning the queue."""

    not_before: float = 0.0
    """Monotonic time before which the message must not be delivered."""


class InMemoryDeadLetter(BaseModel):
    """A message a subscriber gave up on, with the reason."""

    model_config = ConfigDict(frozen=True)

    message: InMemoryMessage
    dead_letter: DeadLetter


@Pod()
class InMemoryEventBroker:
    """Holds one queue and one dead-letter list per subscriber and event.

    Publishing copies the message into the queue of every subscriber bound to
    the event name, so subscribers consume independently. A message published
    while no subscriber is bound is kept only in `published`.
    """

    published: list[InMemoryMessage]
    """Every message ever published, in order, for test assertions."""

    _lock: RLock
    _queues: dict[SubscriptionKey, deque[InMemoryMessage]]
    _dead_letters: dict[SubscriptionKey, list[InMemoryDeadLetter]]
    _in_flight: int
    _busy: set[SubscriptionKey]
    _drains: list[Callable[[], int]]
    _async_drains: list[Callable[[], Awaitable[int]]]

    def __init__(self) -> None:
        self.published = []
        self._lock = RLock()
        self._queues = {}
        self._dead_letters = {}
        self._in_flight = 0
        self._busy = set()
        self._drains = []
        self._async_drains = []

    def bind(self, key: SubscriptionKey) -> None:
        """Create the queue of a subscriber; later publishes are copied into it."""
        with self._lock:
            self._queues.setdefault(key, deque())
            self._dead_letters.setdefault(key, [])

    def attach(self, drain: Callable[[], int]) -> None:
        """Let `drain` reach a sync consumer bound to this broker."""
        self._drains.append(drain)

    def attach_async(self, drain: Callable[[], Awaitable[int]]) -> None:
        """Let `drain_async` reach an async consumer bound to this broker."""
        self._async_drains.append(drain)

    def publish(self, message: InMemoryMessage) -> None:
        """Copy a message into the queue of every subscriber of its event name."""
        with self._lock:
            self.published.append(message)
            for (event_name, _), queue in self._queues.items():
                if event_name == message.event_name:
                    queue.append(message)

    def take(
        self, key: SubscriptionKey, now: float, head_only: bool
    ) -> InMemoryMessage | None:
        """Remove and return the next deliverable message of one queue.

        Args:
            key: Queue to read.
            now: Current monotonic time.
            head_only: Only the oldest message may be taken, so a waiting retry
                blocks the messages behind it and order is preserved. The queue
                then also stays closed to other consumers until `done`.

        Returns:
            A due message, counted as in flight until `done`, or None.
        """
        with self._lock:
            if key in self._busy:
                return None
            queue = self._queues[key]
            for index, message in enumerate(queue):
                if message.not_before <= now:
                    del queue[index]
                    self._in_flight += 1
                    if head_only:
                        self._busy.add(key)
                    return message
                if head_only:
                    return None
            return None

    def done(self, key: SubscriptionKey) -> None:
        """Mark a taken message as settled, after any requeue or dead-letter."""
        with self._lock:
            self._in_flight -= 1
            self._busy.discard(key)

    def requeue_front(self, key: SubscriptionKey, message: InMemoryMessage) -> None:
        """Put a message back as the oldest one of its queue."""
        with self._lock:
            self._queues[key].appendleft(message)

    def requeue_back(self, key: SubscriptionKey, message: InMemoryMessage) -> None:
        """Put a message back behind everything already queued."""
        with self._lock:
            self._queues[key].append(message)

    def next_due_in(
        self, keys: list[SubscriptionKey], now: float, head_only: bool
    ) -> float | None:
        """Return seconds until a queued message becomes deliverable.

        Args:
            keys: Queues to inspect.
            now: Current monotonic time.
            head_only: Only the oldest message of each queue can become
                deliverable, matching `take`. Queues another consumer is
                handling are skipped.

        Returns:
            None when the given queues are empty.
        """
        with self._lock:
            waits = [
                max(message.not_before - now, 0.0)
                for key in keys
                if key not in self._busy
                for message in (
                    list(self._queues[key])[:1] if head_only else self._queues[key]
                )
            ]
        return min(waits) if waits else None

    def add_dead_letter(self, key: SubscriptionKey, entry: InMemoryDeadLetter) -> None:
        """Store a message a subscriber gave up on."""
        with self._lock:
            self._dead_letters[key].append(entry)

    def take_dead_letters(
        self, key: SubscriptionKey, limit: int | None
    ) -> list[InMemoryDeadLetter]:
        """Remove and return up to `limit` oldest dead letters of one subscriber."""
        with self._lock:
            entries = self._dead_letters[key]
            count = len(entries) if limit is None else min(limit, len(entries))
            taken = entries[:count]
            del entries[:count]
            return taken

    def dead_letters(
        self, event_name: str, subscriber: SubscriberName | None = None
    ) -> list[InMemoryDeadLetter]:
        """Return the dead letters one subscriber holds for an event name."""
        with self._lock:
            return list(self._dead_letters.get((event_name, subscriber), []))

    def queued(
        self, event_name: str, subscriber: SubscriberName | None = None
    ) -> list[InMemoryMessage]:
        """Return the messages still waiting in one subscriber queue."""
        with self._lock:
            return list(self._queues.get((event_name, subscriber), []))

    @property
    def idle(self) -> bool:
        """Whether no message is queued or being handled."""
        with self._lock:
            return self._in_flight == 0 and not any(self._queues.values())

    def drain(self) -> int:
        """Deliver through the sync consumers until they make no progress.

        Messages queued for async subscribers are left for `drain_async`. A
        message a background consumer is still handling is waited for, so the
        effects of every delivery are visible when this returns.

        Returns:
            Number of deliveries made by this call.
        """
        total = 0
        while True:
            delivered = sum(drain() for drain in self._drains)
            total += delivered
            if delivered:
                continue
            if not self._handling:
                return total
            sleep(IN_FLIGHT_POLL_INTERVAL)

    async def drain_async(self) -> int:
        """Deliver through every consumer until the broker makes no progress.

        Handlers may publish further events; those are delivered as well. A
        message a background consumer is still handling is waited for, so the
        effects of every delivery are visible when this returns.

        Returns:
            Number of deliveries made by this call.
        """
        total = 0
        while True:
            delivered = sum(drain() for drain in self._drains)
            for drain_async in self._async_drains:
                delivered += await drain_async()
            total += delivered
            if delivered:
                continue
            if not self._handling:
                return total
            await async_sleep(IN_FLIGHT_POLL_INTERVAL)

    @property
    def _handling(self) -> bool:
        with self._lock:
            return self._in_flight > 0
