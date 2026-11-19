from collections.abc import Sequence
from contextvars import ContextVar

from spakky.core.pod.annotations.pod import Pod
from spakky.domain.models.aggregate_root import AbstractAggregateRoot

from spakky.data.persistency.error import AggregateBufferNotOpenError


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
    buffer is a shared list: a child task or thread that inherited the
    execution context collects into the buffer of the transaction it joined,
    while a buffer it opens itself (``REQUIRES_NEW``) stays in its own context.
    The first element is the base buffer used outside any transaction.
    """

    _buffers: ContextVar[tuple[list[AbstractAggregateRoot], ...]]
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
        self._current_buffers()[-1].append(aggregate)

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
        return list(self._current_buffers()[-1])

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
        self._current_buffers()[-1].clear()

    def begin_transaction(self) -> None:
        """Open an empty buffer for a new physical transaction."""
        self._buffers.set((*self._current_buffers(), []))

    def commit_transaction(self) -> None:
        """Close the current buffer and hand its aggregates over for publishing.

        Called right after the physical transaction committed.

        Raises:
            AggregateBufferNotOpenError: No transaction buffer is open.
        """
        buffers = self._open_buffers()
        self._buffers.set(buffers[:-1])
        self._committed.set((*self._committed.get(), *buffers[-1]))

    def discard_transaction(self) -> None:
        """Close the current buffer and drop its aggregates (rolled back).

        Raises:
            AggregateBufferNotOpenError: No transaction buffer is open.
        """
        self._buffers.set(self._open_buffers()[:-1])

    def drain_committed(self) -> Sequence[AbstractAggregateRoot]:
        """Take the aggregates of the transactions committed so far.

        Returns:
            Aggregates handed over by ``commit_transaction()`` since the last
            drain, in collection order.
        """
        committed = list(self._committed.get())
        self._committed.set(())
        return committed

    def _current_buffers(self) -> tuple[list[AbstractAggregateRoot], ...]:
        buffers = self._buffers.get()
        if len(buffers) == 0:
            # The base buffer is created per execution context on first use so
            # that contexts never share a default list.
            buffers = ([],)
            self._buffers.set(buffers)
        return buffers

    def _open_buffers(self) -> tuple[list[AbstractAggregateRoot], ...]:
        buffers = self._current_buffers()
        if len(buffers) == 1:
            raise AggregateBufferNotOpenError()
        return buffers
