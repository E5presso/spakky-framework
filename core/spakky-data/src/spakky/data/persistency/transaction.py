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
    TransactionNotActiveError,
    TransactionRollbackOnlyError,
)


class Propagation(StrEnum):
    """How a transaction scope relates to a transaction already in progress."""

    REQUIRED = "required"
    """Join the transaction in progress, or start a new one when there is none."""

    REQUIRES_NEW = "requires_new"
    """Always start a separate transaction that commits on its own."""


@dataclass(slots=True)
class PhysicalTransaction:
    """Shared, mutable state of one physical transaction.

    A physical transaction is the unit that is actually opened, committed or
    rolled back. Every scope that joins it, including scopes running in child
    tasks or threads that inherited the execution context, refers to the same
    object, so a failure recorded by any of them is seen by the scope that
    opened it.
    """

    rollback_only: bool = False
    """True once a joined scope exited with an exception; commit is refused."""


@dataclass(frozen=True, slots=True)
class TransactionFrame:
    """One open transaction scope in the current execution context.

    Frames are kept in an immutable tuple stored in a ``ContextVar``. A child
    task or thread copies the tuple, so scopes it opens (``REQUIRES_NEW``)
    stay in its own context, while scopes it joins still point at the shared
    ``PhysicalTransaction`` of the parent.
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
        """Whether a transaction scope is open in the current context."""
        return len(self._frames.get()) > 0

    @property
    def is_rollback_only(self) -> bool:
        """Whether the current physical transaction can only be rolled back."""
        frames = self._frames.get()
        return len(frames) > 0 and frames[-1].transaction.rollback_only

    def joins(self, propagation: Propagation) -> bool:
        """Tell whether a scope begun now would join the transaction in progress.

        Args:
            propagation: Propagation of the scope about to begin.

        Returns:
            True when the scope would join, False when it would open a new
            physical transaction.
        """
        return propagation is Propagation.REQUIRED and self.is_active

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
        if self.joins(propagation):
            self._frames.set(
                (*frames, TransactionFrame(frames[-1].transaction, owner=False))
            )
            return
        self.initialize()
        self._frames.set((*frames, TransactionFrame(PhysicalTransaction(), owner=True)))

    @final
    def _finish(self, error: BaseException | None) -> None:
        frames = self._frames.get()
        if not frames:
            raise TransactionNotActiveError()
        top = frames[-1]
        self._frames.set(frames[:-1])
        if not top.owner:
            if error is not None:
                top.transaction.rollback_only = True
            return
        if error is not None:
            try:
                self.rollback()
            finally:
                self.dispose()
            return
        if top.transaction.rollback_only:
            try:
                self.rollback()
            finally:
                self.dispose()
            raise TransactionRollbackOnlyError()
        try:
            if self.autocommit_enabled:
                self.commit()
        except BaseException:
            self.rollback()
            raise
        finally:
            self.dispose()

    @abstractmethod
    def initialize(self) -> None:
        """Open a new physical transaction (e.g. open a session).

        Called for the outermost scope and for every ``REQUIRES_NEW`` scope.
        """
        ...

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
        """Whether a transaction scope is open in the current context."""
        return len(self._frames.get()) > 0

    @property
    def is_rollback_only(self) -> bool:
        """Whether the current physical transaction can only be rolled back."""
        frames = self._frames.get()
        return len(frames) > 0 and frames[-1].transaction.rollback_only

    def joins(self, propagation: Propagation) -> bool:
        """Tell whether a scope begun now would join the transaction in progress.

        Args:
            propagation: Propagation of the scope about to begin.

        Returns:
            True when the scope would join, False when it would open a new
            physical transaction.
        """
        return propagation is Propagation.REQUIRED and self.is_active

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
        if self.joins(propagation):
            self._frames.set(
                (*frames, TransactionFrame(frames[-1].transaction, owner=False))
            )
            return
        await self.initialize()
        self._frames.set((*frames, TransactionFrame(PhysicalTransaction(), owner=True)))

    @final
    async def _finish(self, error: BaseException | None) -> None:
        frames = self._frames.get()
        if not frames:
            raise TransactionNotActiveError()
        top = frames[-1]
        self._frames.set(frames[:-1])
        if not top.owner:
            if error is not None:
                top.transaction.rollback_only = True
            return
        if error is not None:
            try:
                await self.rollback()
            finally:
                await self.dispose()
            return
        if top.transaction.rollback_only:
            try:
                await self.rollback()
            finally:
                await self.dispose()
            raise TransactionRollbackOnlyError()
        try:
            if self.autocommit_enabled:
                await self.commit()
        except BaseException:
            await self.rollback()
            raise
        finally:
            await self.dispose()

    @abstractmethod
    async def initialize(self) -> None:
        """Open a new physical transaction (e.g. open a session).

        Called for the outermost scope and for every ``REQUIRES_NEW`` scope.
        """
        ...

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
