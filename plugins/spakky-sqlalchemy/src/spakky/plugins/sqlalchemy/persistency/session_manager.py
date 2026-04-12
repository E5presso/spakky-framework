from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from typing_extensions import override

from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
    ConnectionManager,
)
from spakky.plugins.sqlalchemy.persistency.error import (
    AbstractSpakkySqlAlchemyPersistencyError,
)
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
)
from sqlalchemy.orm import Session, scoped_session, sessionmaker


class SessionNotInitializedError(AbstractSpakkySqlAlchemyPersistencyError):
    """Raised when trying to access a session that has not been initialized."""

    message = (
        "Session has not been initialized. Call 'open()' before accessing the session."
    )


@Pod()
class SessionManager(IApplicationContextAware):
    """Manages scoped synchronous SQLAlchemy sessions."""

    _application_context: IApplicationContext
    _engine: Engine
    _scoped_session: scoped_session[Session]
    _current_session: Session | None

    @override
    def set_application_context(self, application_context: IApplicationContext) -> None:
        self._application_context = application_context
        self._scoped_session = scoped_session(
            session_factory=sessionmaker(
                bind=self._engine,
                expire_on_commit=False,
            ),
            scopefunc=self._application_context.get_context_id,
        )

    def __init__(self, connection_manager: ConnectionManager) -> None:
        """Initialize with engine from connection manager."""
        self._engine = connection_manager.connection
        self._current_session = None

    @property
    def session(self) -> Session:
        if self._current_session is None:
            raise SessionNotInitializedError()
        return self._current_session

    def open(self) -> None:
        """Open a new scoped session."""
        self._current_session = self._scoped_session()

    def close(self) -> None:
        """Close the current session and remove the scoped session."""
        if self._current_session is not None:
            self._current_session.close()
        self._scoped_session.remove()
        self._current_session = None


@Pod()
class AsyncSessionManager(IApplicationContextAware):
    """Manages scoped asynchronous SQLAlchemy sessions."""

    _application_context: IApplicationContext
    _engine: AsyncEngine
    _scoped_session: async_scoped_session[AsyncSession]
    _current_session: AsyncSession | None

    @override
    def set_application_context(self, application_context: IApplicationContext) -> None:
        self._application_context = application_context
        self._scoped_session = async_scoped_session(
            session_factory=async_sessionmaker(
                bind=self._engine,
                expire_on_commit=False,
            ),
            scopefunc=self._application_context.get_context_id,
        )

    def __init__(self, connection_manager: AsyncConnectionManager) -> None:
        """Initialize with engine from async connection manager."""
        self._engine = connection_manager.connection
        self._current_session = None

    @property
    def session(self) -> AsyncSession:
        if self._current_session is None:
            raise SessionNotInitializedError()
        return self._current_session

    async def open(self) -> None:
        """Open a new scoped async session."""
        self._current_session = self._scoped_session()

    async def close(self) -> None:
        """Close the current session and remove the scoped async session."""
        if self._current_session is not None:
            await self._current_session.close()
        await self._scoped_session.remove()
        self._current_session = None
