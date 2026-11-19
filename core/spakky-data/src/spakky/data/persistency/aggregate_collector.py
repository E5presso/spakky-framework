from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field

from spakky.core.pod.annotations.pod import Pod
from spakky.domain.models.aggregate_root import AbstractAggregateRoot

from spakky.data.persistency.error import (
    AggregateBufferNotOpenError,
    TransactionAlreadyFinishedError,
)
from spakky.data.persistency.transaction import PhysicalTransaction


@dataclass(eq=False, slots=True)
class AggregateBuffer:
    """Aggregates collected by one physical transaction.

    The buffer is bound to the physical transaction it collects for. That
    object is shared by every execution context that copied the buffer stack,
    so the end of the transaction is seen by child tasks and threads that
    still hold the buffer, at the same moment as by its session.
    """

    transaction: PhysicalTransaction | None
    """The physical transaction the aggregates belong to.

    ``None`` (not applicable) for the base buffer used outside any
    transaction, which never finishes.
    """

    aggregates: list[AbstractAggregateRoot] = field(
        default_factory=list[AbstractAggregateRoot]
    )
    """Aggregates collected so far, in collection order."""

    released: bool = False
    """True once ``commit_transaction()`` or ``discard_transaction()`` took it."""


@Pod(scope=Pod.Scope.CONTEXT)
class AggregateCollector:
    """Context-scoped collector with execution-local aggregate buffers.

    Aggregates are buffered per physical transaction. ``@Transactional`` opens
    a buffer whenever its scope opens a physical transaction (the outermost
    scope or a ``Propagation.REQUIRES_NEW`` scope) and, when its scope joins a
    transaction, binds the current context to the buffer of that transaction.
    When a physical transaction commits, its buffer is handed over and stays
    available through ``drain_committed()`` until the domain events are
    published.

    The stack of buffers is an immutable tuple in a ``ContextVar`` that
    mirrors the ``@Transactional`` scopes of the context, but each buffer is a
    shared object: a child task or thread that inherited the execution context
    collects into the buffer of the transaction its scope belongs to, while a
    buffer it opens itself (``REQUIRES_NEW``) stays in its own context. Once
    that transaction has finished (``PhysicalTransaction.finished``), the
    buffer refuses new aggregates instead of falling back to another buffer,
    so an aggregate is never published with a transaction its write did not
    belong to. The first element is the base buffer used outside any
    transaction; it never finishes.
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
        the physical transaction of the current scope.

        Args:
            aggregate: The aggregate to track.

        Raises:
            TransactionAlreadyFinishedError: The transaction of the current
                scope has already committed or rolled back.

        Example:
            >>> collector = AggregateCollector()
            >>> user = User.create(name="Alice")
            >>> collector.collect(user)
        """
        self._usable_buffer().aggregates.append(aggregate)

    def all(self) -> Sequence[AbstractAggregateRoot]:
        """Get the aggregates tracked by the physical transaction of the scope.

        Returns:
            Sequence of tracked aggregates.

        Raises:
            TransactionAlreadyFinishedError: The transaction of the current
                scope has already committed or rolled back.

        Example:
            >>> collector = AggregateCollector()
            >>> user = User.create(name="Bob")
            >>> collector.collect(user)
            >>> len(collector.all())
            1
        """
        return list(self._usable_buffer().aggregates)

    def clear(self) -> None:
        """Clear the aggregates tracked by the physical transaction of the scope.

        Raises:
            TransactionAlreadyFinishedError: The transaction of the current
                scope has already committed or rolled back.

        Example:
            >>> collector = AggregateCollector()
            >>> user = User.create(name="Charlie")
            >>> collector.collect(user)
            >>> collector.clear()
            >>> len(collector.all())
            0
        """
        self._usable_buffer().aggregates.clear()

    def begin_transaction(self, transaction: PhysicalTransaction) -> None:
        """Open an empty buffer for a physical transaction a scope just opened.

        Args:
            transaction: The physical transaction opened by the scope.
        """
        self._buffers.set(
            (*self._current_buffers(), AggregateBuffer(transaction=transaction))
        )

    def join_transaction(self, transaction: PhysicalTransaction) -> None:
        """Collect into the buffer of a transaction a scope just joined.

        The joined transaction may be below the innermost buffer when the
        innermost transaction has already finished. A transaction opened
        without ``@Transactional`` (``scope()`` used directly) has no buffer;
        the scope then keeps collecting where the enclosing scope collects.

        Args:
            transaction: The physical transaction joined by the scope.
        """
        buffers = self._current_buffers()
        joined = next(
            (
                buffer
                for buffer in reversed(buffers)
                if buffer.transaction is transaction
            ),
            buffers[-1],
        )
        self._buffers.set((*buffers, joined))

    def leave_transaction(self) -> None:
        """Stop collecting for the transaction joined by ``join_transaction()``.

        Raises:
            AggregateBufferNotOpenError: No transaction buffer is open.
        """
        buffers = self._current_buffers()
        if len(buffers) == 1:
            raise AggregateBufferNotOpenError()
        self._buffers.set(buffers[:-1])

    def commit_transaction(self) -> None:
        """Hand the aggregates of the current buffer over for publishing.

        Called right after the physical transaction committed.

        Raises:
            AggregateBufferNotOpenError: No transaction buffer is open.
        """
        buffer = self._release_buffer()
        self._committed.set((*self._committed.get(), *buffer.aggregates))

    def discard_transaction(self) -> None:
        """Drop the aggregates of the current buffer (rolled back).

        Raises:
            AggregateBufferNotOpenError: No transaction buffer is open.
        """
        self._release_buffer()

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
            buffers = (AggregateBuffer(transaction=None),)
            self._buffers.set(buffers)
        return buffers

    def _usable_buffer(self) -> AggregateBuffer:
        buffer = self._current_buffers()[-1]
        if buffer.transaction is not None and buffer.transaction.finished:
            raise TransactionAlreadyFinishedError()
        return buffer

    def _release_buffer(self) -> AggregateBuffer:
        buffers = self._current_buffers()
        buffer = buffers[-1]
        if len(buffers) == 1 or buffer.released:
            raise AggregateBufferNotOpenError()
        self._buffers.set(buffers[:-1])
        buffer.released = True
        return buffer
