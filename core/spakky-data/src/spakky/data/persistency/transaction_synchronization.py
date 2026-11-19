import logging
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field

from spakky.core.pod.annotations.pod import Pod

from spakky.data.persistency.error import TransactionSynchronizationNotOpenError
from spakky.data.persistency.transaction import PhysicalTransaction

logger = logging.getLogger(__name__)

type AfterCommitCallback = Callable[[], None]
"""Work to run once the physical transaction it was registered in has committed."""


@dataclass(eq=False, slots=True)
class SynchronizationFrame:
    """After-commit callbacks registered in one physical transaction.

    The frame is bound to the physical transaction it waits for, like an
    ``AggregateBuffer``. That object is shared by every execution context that
    copied the frame stack, so the end of the transaction is seen by child
    tasks and threads that still hold the frame, at the same moment as by its
    session and its aggregate buffer.
    """

    transaction: PhysicalTransaction
    """The physical transaction whose commit the callbacks wait for."""

    callbacks: list[AfterCommitCallback] = field(
        default_factory=list[AfterCommitCallback]
    )
    """Callbacks registered so far, in registration order."""

    released: bool = False
    """True once ``commit_transaction()`` or ``discard_transaction()`` took it."""


@Pod()
class TransactionSynchronization:
    """Execution-local after-commit callbacks, kept per physical transaction.

    ``@Transactional`` opens a frame whenever its scope opens a physical
    transaction (the outermost scope or a ``Propagation.REQUIRES_NEW`` scope)
    and, when its scope joins a transaction, binds the current context to the
    frame of that transaction — the same decisions it makes for the
    ``AggregateCollector`` buffers. When the physical transaction actually
    commits, its callbacks run once; when it rolls back, or finishes without
    committing (``autocommit=False``), they are dropped.

    Infrastructure inside the framework uses this to react to a commit — for
    example the outbox relay is woken to send the messages that the committed
    transaction stored. Applications do not call it.

    The stack of frames is an immutable tuple in a ``ContextVar`` that mirrors
    the ``@Transactional`` scopes of the context, but each frame is a shared
    object: a child task or thread that inherited the execution context
    registers into the frame of the transaction its scope belongs to. Once
    that transaction has finished (``PhysicalTransaction.finished``) the frame
    takes no callbacks, so a child that outlives the transaction never
    registers work that would already have run or been dropped.
    """

    _frames: ContextVar[tuple[SynchronizationFrame | None, ...]]
    """Frames per ``@Transactional`` scope; ``None`` where the scope joined a
    transaction opened without ``@Transactional`` (not applicable)."""

    def __init__(self) -> None:
        self._frames = ContextVar("spakky_transaction_synchronization", default=())

    @property
    def is_active(self) -> bool:
        """Whether the current scope belongs to a transaction that is still open."""
        return self._usable_frame() is not None

    def register_after_commit(self, callback: AfterCommitCallback) -> None:
        """Run ``callback`` after the physical transaction of the scope commits.

        Registering the same callback twice in one transaction runs it once.

        Args:
            callback: Work to run after the commit.

        Raises:
            TransactionSynchronizationNotOpenError: The current scope belongs
                to no open transaction, so there is no commit to wait for.
        """
        frame = self._usable_frame()
        if frame is None:
            raise TransactionSynchronizationNotOpenError()
        if callback in frame.callbacks:
            return
        frame.callbacks.append(callback)

    def begin_transaction(self, transaction: PhysicalTransaction) -> None:
        """Open an empty frame for a physical transaction a scope just opened.

        Args:
            transaction: The physical transaction opened by the scope.
        """
        self._frames.set(
            (*self._frames.get(), SynchronizationFrame(transaction=transaction))
        )

    def join_transaction(self, transaction: PhysicalTransaction) -> None:
        """Register into the frame of a transaction a scope just joined.

        A transaction opened without ``@Transactional`` (``scope()`` used
        directly) has no frame; the scope then keeps registering where the
        enclosing scope registers, or nowhere when there is none — its
        messages are left to the next poll.

        Args:
            transaction: The physical transaction joined by the scope.
        """
        frames = self._frames.get()
        joined = next(
            (
                frame
                for frame in reversed(frames)
                if frame is not None and frame.transaction is transaction
            ),
            frames[-1] if frames else None,
        )
        self._frames.set((*frames, joined))

    def leave_transaction(self) -> None:
        """Stop registering for the transaction joined by ``join_transaction()``.

        Raises:
            TransactionSynchronizationNotOpenError: No frame is open.
        """
        frames = self._frames.get()
        if not frames:
            raise TransactionSynchronizationNotOpenError()
        self._frames.set(frames[:-1])

    def commit_transaction(self) -> None:
        """Release the current frame and run its callbacks.

        Called right after the physical transaction committed. A failing
        callback is logged and the rest still run: the commit already happened
        and cannot be undone, so the caller must not be told it failed.

        Raises:
            TransactionSynchronizationNotOpenError: No frame is open.
        """
        frame = self._release_frame()
        for callback in frame.callbacks:
            try:
                callback()
            except Exception:
                logger.exception("After-commit callback %r failed", callback)

    def discard_transaction(self) -> None:
        """Release the current frame without running its callbacks.

        Called when the physical transaction rolled back or did not commit.

        Raises:
            TransactionSynchronizationNotOpenError: No frame is open.
        """
        self._release_frame()

    def _usable_frame(self) -> SynchronizationFrame | None:
        """Find the frame of the current scope while its transaction is open.

        Returns:
            The frame to register into, or ``None`` (none applicable) outside
            any ``@Transactional`` scope or once its transaction has finished.
        """
        frames = self._frames.get()
        frame = frames[-1] if frames else None
        if frame is None or frame.transaction.finished:
            return None
        return frame

    def _release_frame(self) -> SynchronizationFrame:
        frames = self._frames.get()
        frame = frames[-1] if frames else None
        if frame is None or frame.released:
            raise TransactionSynchronizationNotOpenError()
        self._frames.set(frames[:-1])
        frame.released = True
        return frame
