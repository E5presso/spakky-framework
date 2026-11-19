from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field

from spakky.core.pod.annotations.pod import Pod
from spakky.domain.models.aggregate_root import AbstractAggregateRoot

from spakky.data.persistency.error import AggregateBufferNotOpenError


@dataclass(slots=True)
class AggregateBuffer:
    """Aggregates collected by one physical transaction.

    The buffer object is shared by every execution context that copied it, so
    closing it in the context that owns the transaction is seen by child tasks
    and threads that still hold it.
    """

    aggregates: list[AbstractAggregateRoot] = field(
        default_factory=list[AbstractAggregateRoot]
    )
    """Aggregates collected so far, in collection order."""

    closed: bool = False
    """True once the transaction committed or rolled back; no longer collects."""


@Pod(scope=Pod.Scope.CONTEXT)
class AggregateCollector:
    """Context-scoped collector with execution-local aggregate buffers.

    Aggregates are buffered per physical transaction. ``@Transactional`` opens
    a buffer whenever it opens a physical transaction (the outermost scope or a
    ``Propagation.REQUIRES_NEW`` scope) and joined scopes keep collecting into
    the buffer of the transaction they joined. When a physical transaction
    commits, its buffer is handed over and stays available through
    ``drain_committed()`` until the domain events are published.

    The stack of buffers is an immutable tuple in a ``ContextVar`` but each
    buffer is a shared object: a child task or thread that inherited the
    execution context collects into the buffer of the transaction it joined,
    while a buffer it opens itself (``REQUIRES_NEW``) stays in its own context.
    Buffers closed by the transaction that owned them are skipped, so a child
    that outlives that transaction never collects into a buffer that was
    already handed over. The first element is the base buffer used outside any
    transaction; it is never closed.
    """

    _buffers: ContextVar[tuple[AggregateBuffer, ...]]
    _committed: ContextVar[tuple[AbstractAggregateRoot, ...]]

    def __init__(self) -> None:
        self._buffers = ContextVar("spakky_collected_aggregates", default=())
        self._committed = ContextVar("spakky_committed_aggregates", default=())

    def collect(self, aggregate: AbstractAggregateRoot) -> None:
        """Track an aggregate that was saved during the transaction.

        This method is called by Repository implementations after saving
        an aggregate to the database. The aggregate is added to the buffer of
        the physical transaction in progress.

        Args:
            aggregate: The aggregate to track.

        Example:
            >>> collector = AggregateCollector()
            >>> user = User.create(name="Alice")
            >>> collector.collect(user)
        """
        self._live_buffer().aggregates.append(aggregate)

    def all(self) -> Sequence[AbstractAggregateRoot]:
        """Get the aggregates tracked by the physical transaction in progress.

        Returns:
            Sequence of tracked aggregates.

        Example:
            >>> collector = AggregateCollector()
            >>> user = User.create(name="Bob")
            >>> collector.collect(user)
            >>> len(collector.all())
            1
        """
        return list(self._live_buffer().aggregates)

    def clear(self) -> None:
        """Clear the aggregates tracked by the physical transaction in progress.

        Example:
            >>> collector = AggregateCollector()
            >>> user = User.create(name="Charlie")
            >>> collector.collect(user)
            >>> collector.clear()
            >>> len(collector.all())
            0
        """
        self._live_buffer().aggregates.clear()

    def begin_transaction(self) -> None:
        """Open an empty buffer for a new physical transaction."""
        self._buffers.set((*self._current_buffers(), AggregateBuffer()))

    def commit_transaction(self) -> None:
        """Close the current buffer and hand its aggregates over for publishing.

        Called right after the physical transaction committed.

        Raises:
            AggregateBufferNotOpenError: No transaction buffer is open.
        """
        buffers = self._open_buffers()
        self._buffers.set(buffers[:-1])
        buffers[-1].closed = True
        self._committed.set((*self._committed.get(), *buffers[-1].aggregates))

    def discard_transaction(self) -> None:
        """Close the current buffer and drop its aggregates (rolled back).

        Raises:
            AggregateBufferNotOpenError: No transaction buffer is open.
        """
        buffers = self._open_buffers()
        self._buffers.set(buffers[:-1])
        buffers[-1].closed = True

    def drain_committed(self) -> Sequence[AbstractAggregateRoot]:
        """Take the aggregates of the transactions committed so far.

        Returns:
            Aggregates handed over by ``commit_transaction()`` since the last
            drain, in collection order.
        """
        committed = list(self._committed.get())
        self._committed.set(())
        return committed

    def _current_buffers(self) -> tuple[AggregateBuffer, ...]:
        buffers = self._buffers.get()
        if len(buffers) == 0:
            # The base buffer is created per execution context on first use so
            # that contexts never share a default buffer.
            buffers = (AggregateBuffer(),)
            self._buffers.set(buffers)
        return buffers

    def _live_buffer(self) -> AggregateBuffer:
        # The base buffer is never closed, so the search always finds one.
        return next(
            buffer for buffer in reversed(self._current_buffers()) if not buffer.closed
        )

    def _open_buffers(self) -> tuple[AggregateBuffer, ...]:
        buffers = self._current_buffers()
        if len(buffers) == 1 or buffers[-1].closed:
            raise AggregateBufferNotOpenError()
        return buffers
