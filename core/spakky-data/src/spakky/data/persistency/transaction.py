from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self, final

from spakky.core.common.interfaces.disposable import IAsyncDisposable, IDisposable


class AbstractTransaction(IDisposable, ABC):
    """Abstract base for synchronous transaction context managers."""

    autocommit_enabled: bool

    def __init__(self, autocommit: bool = True) -> None:
        """Initialize the transaction.

        Args:
            autocommit: Whether to auto-commit on successful exit.
        """
        self.autocommit_enabled = autocommit

    @final
    def __enter__(self) -> Self:
        self.initialize()
        return self

    @final
    def __exit__(
        self,
        __exc_type: type[BaseException] | None,
        __exc_value: BaseException | None,
        __traceback: TracebackType | None,
    ) -> bool | None:
        if __exc_value is not None:
            self.rollback()
            self.dispose()
            return
        try:
            if self.autocommit_enabled:
                self.commit()
        except:
            self.rollback()
            raise
        finally:
            self.dispose()

    @abstractmethod
    def initialize(self) -> None:
        """Initialize the transaction (e.g. open a session)."""
        ...

    @abstractmethod
    def dispose(self) -> None:
        """Dispose the transaction resources (e.g. close a session)."""
        ...

    @abstractmethod
    def commit(self) -> None:
        """Commit the current transaction."""
        ...

    @abstractmethod
    def rollback(self) -> None:
        """Roll back the current transaction."""
        ...


class AbstractAsyncTransaction(IAsyncDisposable, ABC):
    """Abstract base for asynchronous transaction context managers."""

    autocommit_enabled: bool

    def __init__(self, autocommit: bool = True) -> None:
        """Initialize the async transaction.

        Args:
            autocommit: Whether to auto-commit on successful exit.
        """
        self.autocommit_enabled = autocommit

    @final
    async def __aenter__(self) -> Self:
        await self.initialize()
        return self

    @final
    async def __aexit__(
        self,
        __exc_type: type[BaseException] | None,
        __exc_value: BaseException | None,
        __traceback: TracebackType | None,
    ) -> bool | None:
        if __exc_value is not None:
            await self.rollback()
            await self.dispose()
            return
        try:
            if self.autocommit_enabled:
                await self.commit()
        except:
            await self.rollback()
            raise
        finally:
            await self.dispose()

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the async transaction (e.g. open a session)."""
        ...

    @abstractmethod
    async def dispose(self) -> None:
        """Dispose the async transaction resources."""
        ...

    @abstractmethod
    async def commit(self) -> None:
        """Commit the current async transaction."""
        ...

    @abstractmethod
    async def rollback(self) -> None:
        """Roll back the current async transaction."""
        ...
