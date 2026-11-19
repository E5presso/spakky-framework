from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
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


@dataclass(frozen=True, slots=True)
class TransactionFrame:
    """State of one physical transaction in the current execution context.

    A physical transaction is the unit that is actually opened, committed or
    rolled back. Joined scopes share the frame of the scope they joined.
    """

    depth: int = 1
    """Number of scopes currently participating (1 = only the opening scope)."""

    rollback_only: bool = False
    """True once a joined scope exited with an exception; commit is refused."""


class AbstractTransaction(IDisposable, ABC):
    """Abstract base for synchronous transaction context managers.

    Scopes nest per execution context. ``Propagation.REQUIRED`` joins the
    transaction in progress, and only the scope that opened the physical
    transaction commits, rolls back and disposes it.
    ``Propagation.REQUIRES_NEW`` always opens a separate physical transaction
    through ``initialize()``; implementations must keep the outer one intact
    and restore it in ``dispose()``.
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
        return len(frames) > 0 and frames[-1].rollback_only

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
            top = frames[-1]
            self._frames.set((*frames[:-1], replace(top, depth=top.depth + 1)))
            return
        self.initialize()
        self._frames.set((*frames, TransactionFrame()))

    @final
    def _finish(self, error: BaseException | None) -> None:
        frames = self._frames.get()
        if not frames:
            raise TransactionNotActiveError()
        top = frames[-1]
        if top.depth > 1:
            self._frames.set(
                (
                    *frames[:-1],
                    replace(
                        top,
                        depth=top.depth - 1,
                        rollback_only=top.rollback_only or error is not None,
                    ),
                )
            )
            return
        self._frames.set(frames[:-1])
        if error is not None:
            try:
                self.rollback()
            finally:
                self.dispose()
            return
        if top.rollback_only:
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
        return len(frames) > 0 and frames[-1].rollback_only

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
            top = frames[-1]
            self._frames.set((*frames[:-1], replace(top, depth=top.depth + 1)))
            return
        await self.initialize()
        self._frames.set((*frames, TransactionFrame()))

    @final
    async def _finish(self, error: BaseException | None) -> None:
        frames = self._frames.get()
        if not frames:
            raise TransactionNotActiveError()
        top = frames[-1]
        if top.depth > 1:
            self._frames.set(
                (
                    *frames[:-1],
                    replace(
                        top,
                        depth=top.depth - 1,
                        rollback_only=top.rollback_only or error is not None,
                    ),
                )
            )
            return
        self._frames.set(frames[:-1])
        if error is not None:
            try:
                await self.rollback()
            finally:
                await self.dispose()
            return
        if top.rollback_only:
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
