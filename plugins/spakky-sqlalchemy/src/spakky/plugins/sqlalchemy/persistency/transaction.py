from spakky.core.pod.annotations.pod import Pod
from spakky.data import AbstractAsyncTransaction, AbstractTransaction

from spakky.plugins.sqlalchemy.common.config import SQLAlchemyConnectionConfig
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from typing import override


@Pod()
class Transaction(AbstractTransaction):
    """SQLAlchemy synchronous transaction implementation."""

    _session_manager: SessionManager

    @property
    def session(self) -> Session:
        return self._session_manager.session

    def __init__(
        self,
        config: SQLAlchemyConnectionConfig,
        session_manager: SessionManager,
    ) -> None:
        """Initialize with autocommit config and session manager."""
        super().__init__(autocommit=config.autocommit)
        self._session_manager = session_manager

    @override
    def initialize(self) -> None:
        """Open a new session bound to the new physical transaction."""
        self._session_manager.open(self.current_frame.transaction)

    @override
    def join(self) -> None:
        """Use the session of the joined physical transaction."""
        self._session_manager.join(self.current_frame.transaction)

    @override
    def leave(self) -> None:
        """Stop using the session of the joined physical transaction."""
        self._session_manager.leave()

    @override
    def dispose(self) -> None:
        """Close the top session and return to the one below."""
        self._session_manager.close()

    @override
    def commit(self) -> None:
        """Commit the current session."""
        self._session_manager.session.commit()

    @override
    def rollback(self) -> None:
        """Roll back the current session."""
        self._session_manager.session.rollback()


@Pod()
class AsyncTransaction(AbstractAsyncTransaction):
    """SQLAlchemy asynchronous transaction implementation."""

    _session_manager: AsyncSessionManager

    @property
    def session(self) -> AsyncSession:
        return self._session_manager.session

    def __init__(
        self,
        config: SQLAlchemyConnectionConfig,
        session_manager: AsyncSessionManager,
    ) -> None:
        """Initialize with autocommit config and async session manager."""
        super().__init__(autocommit=config.autocommit)
        self._session_manager = session_manager

    @override
    async def initialize(self) -> None:
        """Open a new async session bound to the new physical transaction."""
        await self._session_manager.open(self.current_frame.transaction)

    @override
    async def join(self) -> None:
        """Use the async session of the joined physical transaction."""
        await self._session_manager.join(self.current_frame.transaction)

    @override
    async def leave(self) -> None:
        """Stop using the async session of the joined physical transaction."""
        await self._session_manager.leave()

    @override
    async def dispose(self) -> None:
        """Close the top async session and return to the one below."""
        await self._session_manager.close()

    @override
    async def commit(self) -> None:
        """Commit the current async session."""
        await self._session_manager.session.commit()

    @override
    async def rollback(self) -> None:
        """Roll back the current async session."""
        await self._session_manager.session.rollback()
