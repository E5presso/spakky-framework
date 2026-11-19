from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import StrEnum
from types import TracebackType
from typing import Self, final

from spakky.core.common.interfaces.disposable import IAsyncDisposable, IDisposable

from spakky.data.persistency.error import (
    TransactionAlreadyFinishedError,
    TransactionNotActiveError,
    TransactionRollbackOnlyError,
)


class Propagation(StrEnum):
    """How a transaction scope relates to a transaction already in progress."""

    REQUIRED = "required"
    """Join the transaction in progress, or start a new one when there is none."""

    REQUIRES_NEW = "requires_new"
    """Always start a separate transaction that commits on its own."""


@dataclass(eq=False, slots=True)
class PhysicalTransaction:
    """Shared, mutable state of one physical transaction.

    A physical transaction is the unit that is actually opened, committed or
    rolled back. Every scope that joins it, including scopes running in child
    tasks or threads that inherited the execution context, refers to the same
    object, so a failure recorded by any of them is seen by the scope that
    opened it, and the end of the transaction is seen by all of them.

    The object is compared by identity. Resources that belong to one physical
    transaction (a session, an aggregate buffer) are bound to it and read its
    ``finished`` flag, so they all stop being handed out at the same moment.
    """

    rollback_only: bool = False
    """True once a joined scope exited with an exception; commit is refused."""

    finished: bool = False
    """True once the opening scope committed or rolled back.

    Set right after the commit or rollback and before ``dispose()`` releases
    the resource. A child task or thread that outlives the opening scope still
    holds frames of this transaction in its copied context. From then on new
    scopes skip it and never join it, and resources bound to it refuse to be
    used, so nothing can be written to or collected for a transaction whose
    outcome is already decided.
    """


@dataclass(frozen=True, slots=True)
class TransactionFrame:
    """One open transaction scope in the current execution context.

    Frames are kept in an immutable tuple stored in a ``ContextVar``. A child
    task or thread copies the tuple, so scopes it opens (``REQUIRES_NEW``)
    stay in its own context, while scopes it joins still point at the shared
    ``PhysicalTransaction`` of the parent. Frames whose transaction has
    finished stay in such a copy but are skipped.
    """

    transaction: PhysicalTransaction
    """The physical transaction this scope belongs to."""

    owner: bool
    """True for the scope that opened the physical transaction."""


class AbstractTransaction(IDisposable, ABC):
    """Abstract base for synchronous transaction context managers.

    Scopes nest per execution context. ``Propagation.REQUIRED`` joins the
    transaction in progress, and only the scope that opened the physical
    transaction commits, rolls back and disposes it.
    ``Propagation.REQUIRES_NEW`` always opens a separate physical transaction
    through ``initialize()``; implementations must keep the outer one intact
    and restore it in ``dispose()``.

    A child task or thread that copied the execution context inherits the
    open scopes. A ``REQUIRED`` scope it begins joins the parent's physical
    transaction, and a failure there marks that transaction rollback-only for
    the parent too. A ``REQUIRES_NEW`` scope it begins stays in its own
    context, so implementations must keep the per-transaction resource (e.g.
    the session) in execution-context-local state, not in state shared by
    every task of a request.

    A child that begins a scope after the transaction it inherited has
    finished does not join it: the scope joins the closest live transaction
    below it or opens a new one. A joined scope that is still open when the
    opening scope finishes raises ``TransactionAlreadyFinishedError`` on exit.

    Implementations bind their resource to the physical transaction instead of
    looking it up on their own: ``initialize()`` binds a new resource to
    ``current_frame.transaction``, ``join()`` binds the current context to the
    resource of the transaction it joined and ``leave()`` undoes that. The
    resource of the current frame is the one to use. Once its transaction is
    ``finished`` it must be refused with ``TransactionAlreadyFinishedError``
    instead of falling back to a resource below it.
    """

    autocommit_enabled: bool
    _frames: ContextVar[tuple[TransactionFrame, ...]]

    def __init__(self, autocommit: bool = True) -> None:
        """Initialize the transaction.

        Args:
            autocommit: Whether to auto-commit on successful exit.
        """
        self.autocommit_enabled = autocommit
        self._frames = ContextVar("spakky_transaction_frames", default=())

    @property
    def is_active(self) -> bool:
        """Whether a live transaction is open in the current context."""
        return self._live_transaction() is not None

    @property
    def is_rollback_only(self) -> bool:
        """Whether the current physical transaction can only be rolled back."""
        transaction = self._live_transaction()
        return transaction is not None and transaction.rollback_only

    @property
    def current_frame(self) -> TransactionFrame:
        """The innermost open scope of the current execution context.

        Returns:
            The frame of that scope. Its ``owner`` tells whether the scope
            opened the physical transaction or joined it.

        Raises:
            TransactionNotActiveError: No scope is open in this context.
        """
        frames = self._frames.get()
        if not frames:
            raise TransactionNotActiveError()
        return frames[-1]

    @final
    def _live_transaction(self) -> PhysicalTransaction | None:
        """Find the innermost physical transaction that has not finished.

        Returns:
            The transaction a ``REQUIRED`` scope would join, or ``None`` (none
            applicable) when every inherited transaction has finished.
        """
        for frame in reversed(self._frames.get()):
            if not frame.transaction.finished:
                return frame.transaction
        return None

    @final
    @contextmanager
    def scope(self, propagation: Propagation = Propagation.REQUIRED) -> Generator[Self]:
        """Run a block inside a transaction scope with the given propagation.

        Args:
            propagation: How the scope relates to a transaction in progress.

        Yields:
            This transaction.

        Raises:
            TransactionRollbackOnlyError: The opening scope finished normally
                but a joined scope had failed, so the transaction was rolled
                back.
            TransactionAlreadyFinishedError: The scope joined a transaction
                that finished before the scope exited.
        """
        self._begin(propagation)
        try:
            yield self
        except BaseException as error:
            self._finish(error)
            raise
        self._finish(None)

    @final
    def __enter__(self) -> Self:
        self._begin(Propagation.REQUIRED)
        return self

    @final
    def __exit__(
        self,
        __exc_type: type[BaseException] | None,
        __exc_value: BaseException | None,
        __traceback: TracebackType | None,
    ) -> bool | None:
        self._finish(__exc_value)
        return None

    @final
    def _begin(self, propagation: Propagation) -> None:
        frames = self._frames.get()
        joined = self._live_transaction()
        if propagation is Propagation.REQUIRED and joined is not None:
            self._frames.set((*frames, TransactionFrame(joined, owner=False)))
            try:
                self.join()
            except BaseException:
                self._frames.set(frames)
                raise
            return
        transaction = PhysicalTransaction()
        self._frames.set((*frames, TransactionFrame(transaction, owner=True)))
        try:
            self.initialize()
        except BaseException:
            transaction.finished = True
            self._frames.set(frames)
            raise

    @final
    def _finish(self, error: BaseException | None) -> None:
        frames = self._frames.get()
        if not frames:
            raise TransactionNotActiveError()
        top = frames[-1]
        self._frames.set(frames[:-1])
        if not top.owner:
            self.leave()
            if top.transaction.finished:
                raise TransactionAlreadyFinishedError()
            if error is not None:
                top.transaction.rollback_only = True
            return
        self._complete(top.transaction, error)

    @final
    def _complete(
        self, transaction: PhysicalTransaction, error: BaseException | None
    ) -> None:
        try:
            if error is not None:
                self.rollback()
            elif transaction.rollback_only:
                self.rollback()
                raise TransactionRollbackOnlyError()
            elif self.autocommit_enabled:
                try:
                    self.commit()
                except BaseException:
                    self.rollback()
                    raise
        finally:
            # The outcome is decided here. Marking it before dispose() closes
            # the transaction for every context at once: a scope begun from
            # now on skips it, and the resources bound to it refuse to be
            # used, even while dispose() is still releasing them.
            transaction.finished = True
            self.dispose()

    @abstractmethod
    def initialize(self) -> None:
        """Open a new physical transaction (e.g. open a session).

        Called for the outermost scope and for every ``REQUIRES_NEW`` scope,
        after its frame was pushed: ``current_frame.transaction`` is the new
        physical transaction to bind the resource to.
        """
        ...

    def join(self) -> None:
        """Bind the current context to the resource of the joined transaction.

        Called when a ``REQUIRED`` scope joins a transaction in progress, after
        its frame was pushed: ``current_frame.transaction`` is the joined
        transaction. It is below the innermost frame when the innermost one
        has already finished. Implementations that keep no resource per
        context leave this as it is.
        """

    def leave(self) -> None:
        """Undo the binding made by ``join()`` when the joined scope exits.

        Implementations that keep no resource per context leave this as it is.
        """

    @abstractmethod
    def dispose(self) -> None:
        """Release the physical transaction opened by the last ``initialize()``."""
        ...

    @abstractmethod
    def commit(self) -> None:
        """Commit the current physical transaction."""
        ...

    @abstractmethod
    def rollback(self) -> None:
        """Roll back the current physical transaction."""
        ...


class AbstractAsyncTransaction(IAsyncDisposable, ABC):
    """Abstract base for asynchronous transaction context managers.

    Scopes nest per execution context. ``Propagation.REQUIRED`` joins the
    transaction in progress, and only the scope that opened the physical
    transaction commits, rolls back and disposes it.
    ``Propagation.REQUIRES_NEW`` always opens a separate physical transaction
    through ``initialize()``; implementations must keep the outer one intact
    and restore it in ``dispose()``.

    A child task or thread that copied the execution context inherits the
    open scopes. A ``REQUIRED`` scope it begins joins the parent's physical
    transaction, and a failure there marks that transaction rollback-only for
    the parent too. A ``REQUIRES_NEW`` scope it begins stays in its own
    context, so implementations must keep the per-transaction resource (e.g.
    the session) in execution-context-local state, not in state shared by
    every task of a request.

    A child that begins a scope after the transaction it inherited has
    finished does not join it: the scope joins the closest live transaction
    below it or opens a new one. A joined scope that is still open when the
    opening scope finishes raises ``TransactionAlreadyFinishedError`` on exit.

    Implementations bind their resource to the physical transaction instead of
    looking it up on their own: ``initialize()`` binds a new resource to
    ``current_frame.transaction``, ``join()`` binds the current context to the
    resource of the transaction it joined and ``leave()`` undoes that. The
    resource of the current frame is the one to use. Once its transaction is
    ``finished`` it must be refused with ``TransactionAlreadyFinishedError``
    instead of falling back to a resource below it.
    """

    autocommit_enabled: bool
    _frames: ContextVar[tuple[TransactionFrame, ...]]

    def __init__(self, autocommit: bool = True) -> None:
        """Initialize the async transaction.

        Args:
            autocommit: Whether to auto-commit on successful exit.
        """
        self.autocommit_enabled = autocommit
        self._frames = ContextVar("spakky_async_transaction_frames", default=())

    @property
    def is_active(self) -> bool:
        """Whether a live transaction is open in the current context."""
        return self._live_transaction() is not None

    @property
    def is_rollback_only(self) -> bool:
        """Whether the current physical transaction can only be rolled back."""
        transaction = self._live_transaction()
        return transaction is not None and transaction.rollback_only

    @property
    def current_frame(self) -> TransactionFrame:
        """The innermost open scope of the current execution context.

        Returns:
            The frame of that scope. Its ``owner`` tells whether the scope
            opened the physical transaction or joined it.

        Raises:
            TransactionNotActiveError: No scope is open in this context.
        """
        frames = self._frames.get()
        if not frames:
            raise TransactionNotActiveError()
        return frames[-1]

    @final
    def _live_transaction(self) -> PhysicalTransaction | None:
        """Find the innermost physical transaction that has not finished.

        Returns:
            The transaction a ``REQUIRED`` scope would join, or ``None`` (none
            applicable) when every inherited transaction has finished.
        """
        for frame in reversed(self._frames.get()):
            if not frame.transaction.finished:
                return frame.transaction
        return None

    @final
    @asynccontextmanager
    async def scope(
        self, propagation: Propagation = Propagation.REQUIRED
    ) -> AsyncGenerator[Self]:
        """Run a block inside a transaction scope with the given propagation.

        Args:
            propagation: How the scope relates to a transaction in progress.

        Yields:
            This transaction.

        Raises:
            TransactionRollbackOnlyError: The opening scope finished normally
                but a joined scope had failed, so the transaction was rolled
                back.
            TransactionAlreadyFinishedError: The scope joined a transaction
                that finished before the scope exited.
        """
        await self._begin(propagation)
        try:
            yield self
        except BaseException as error:
            await self._finish(error)
            raise
        await self._finish(None)

    @final
    async def __aenter__(self) -> Self:
        await self._begin(Propagation.REQUIRED)
        return self

    @final
    async def __aexit__(
        self,
        __exc_type: type[BaseException] | None,
        __exc_value: BaseException | None,
        __traceback: TracebackType | None,
    ) -> bool | None:
        await self._finish(__exc_value)
        return None

    @final
    async def _begin(self, propagation: Propagation) -> None:
        frames = self._frames.get()
        joined = self._live_transaction()
        if propagation is Propagation.REQUIRED and joined is not None:
            self._frames.set((*frames, TransactionFrame(joined, owner=False)))
            try:
                await self.join()
            except BaseException:
                self._frames.set(frames)
                raise
            return
        transaction = PhysicalTransaction()
        self._frames.set((*frames, TransactionFrame(transaction, owner=True)))
        try:
            await self.initialize()
        except BaseException:
            transaction.finished = True
            self._frames.set(frames)
            raise

    @final
    async def _finish(self, error: BaseException | None) -> None:
        frames = self._frames.get()
        if not frames:
            raise TransactionNotActiveError()
        top = frames[-1]
        self._frames.set(frames[:-1])
        if not top.owner:
            await self.leave()
            if top.transaction.finished:
                raise TransactionAlreadyFinishedError()
            if error is not None:
                top.transaction.rollback_only = True
            return
        await self._complete(top.transaction, error)

    @final
    async def _complete(
        self, transaction: PhysicalTransaction, error: BaseException | None
    ) -> None:
        try:
            if error is not None:
                await self.rollback()
            elif transaction.rollback_only:
                await self.rollback()
                raise TransactionRollbackOnlyError()
            elif self.autocommit_enabled:
                try:
                    await self.commit()
                except BaseException:
                    await self.rollback()
                    raise
        finally:
            # The outcome is decided here. Marking it before dispose() closes
            # the transaction for every context at once: a scope begun from
            # now on skips it, and the resources bound to it refuse to be
            # used, even while dispose() is still releasing them.
            transaction.finished = True
            await self.dispose()

    @abstractmethod
    async def initialize(self) -> None:
        """Open a new physical transaction (e.g. open a session).

        Called for the outermost scope and for every ``REQUIRES_NEW`` scope,
        after its frame was pushed: ``current_frame.transaction`` is the new
        physical transaction to bind the resource to.
        """
        ...

    async def join(self) -> None:
        """Bind the current context to the resource of the joined transaction.

        Called when a ``REQUIRED`` scope joins a transaction in progress, after
        its frame was pushed: ``current_frame.transaction`` is the joined
        transaction. It is below the innermost frame when the innermost one
        has already finished. Implementations that keep no resource per
        context leave this as it is.
        """

    async def leave(self) -> None:
        """Undo the binding made by ``join()`` when the joined scope exits.

        Implementations that keep no resource per context leave this as it is.
        """

    @abstractmethod
    async def dispose(self) -> None:
        """Release the physical transaction opened by the last ``initialize()``."""
        ...

    @abstractmethod
    async def commit(self) -> None:
        """Commit the current physical transaction."""
        ...

    @abstractmethod
    async def rollback(self) -> None:
        """Roll back the current physical transaction."""
        ...
