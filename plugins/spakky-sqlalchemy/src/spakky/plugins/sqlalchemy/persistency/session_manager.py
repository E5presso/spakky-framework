from contextvars import ContextVar

from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from typing import override

from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
    ConnectionManager,
)
from spakky.plugins.sqlalchemy.persistency.error import (
    AbstractSpakkySqlAlchemyPersistencyError,
)
from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker


class SessionNotInitializedError(AbstractSpakkySqlAlchemyPersistencyError):
    """Raised when trying to access a session that has not been initialized."""

    message = (
        "Session has not been initialized. Call 'open()' before accessing the session."
    )


@Pod()
class SessionManager(IApplicationContextAware):
    """Manages synchronous SQLAlchemy sessions per execution context.

    Each execution context keeps a stack of sessions. ``open()`` pushes a new
    session (a new physical transaction, e.g. ``Propagation.REQUIRES_NEW``) on
    top of the current one and ``close()`` closes the top session and returns
    to the one below. ``session`` always resolves to the top session.

    The stack is an immutable tuple held in a ``ContextVar``. A child task or
    thread that copied the execution context starts from the parent's stack,
    so it sees the parent's session, but the sessions it opens and closes stay
    in its own context and never replace the session another task is using.
    """

    _application_context: IApplicationContext
    _engine: Engine
    _session_factory: sessionmaker[Session] | None
    _sessions: ContextVar[tuple[Session, ...]]

    @override
    def set_application_context(self, application_context: IApplicationContext) -> None:
        self._application_context = application_context
        self._session_factory = sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
        )

    def __init__(self, connection_manager: ConnectionManager) -> None:
        """Initialize with engine from connection manager."""
        self._engine = connection_manager.connection
        self._session_factory = None
        self._sessions = ContextVar("spakky_sqlalchemy_sessions", default=())

    @property
    def session(self) -> Session:
        if self._session_factory is None:
            raise SessionNotInitializedError()
        stack = self._sessions.get()
        if not stack:
            raise SessionNotInitializedError()
        return stack[-1]

    def open(self) -> None:
        """Open a new session on top of the current context's session stack."""
        if self._session_factory is None:
            raise SessionNotInitializedError()
        self._sessions.set((*self._sessions.get(), self._session_factory()))

    def close(self) -> None:
        """Close the top session of the current context and return to the one below."""
        if self._session_factory is None:
            return
        stack = self._sessions.get()
        if not stack:
            return
        session = stack[-1]
        self._sessions.set(stack[:-1])
        session.close()


@Pod()
class AsyncSessionManager(IApplicationContextAware):
    """Manages asynchronous SQLAlchemy sessions per execution context.

    Each execution context keeps a stack of sessions. ``open()`` pushes a new
    session (a new physical transaction, e.g. ``Propagation.REQUIRES_NEW``) on
    top of the current one and ``close()`` closes the top session and returns
    to the one below. ``session`` always resolves to the top session.

    The stack is an immutable tuple held in a ``ContextVar``. A child task or
    thread that copied the execution context starts from the parent's stack,
    so it sees the parent's session, but the sessions it opens and closes stay
    in its own context and never replace the session another task is using.
    """

    _application_context: IApplicationContext
    _engine: AsyncEngine
    _session_factory: async_sessionmaker[AsyncSession] | None
    _sessions: ContextVar[tuple[AsyncSession, ...]]

    @override
    def set_application_context(self, application_context: IApplicationContext) -> None:
        self._application_context = application_context
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
        )

    def __init__(self, connection_manager: AsyncConnectionManager) -> None:
        """Initialize with engine from async connection manager."""
        self._engine = connection_manager.connection
        self._session_factory = None
        self._sessions = ContextVar("spakky_sqlalchemy_async_sessions", default=())

    @property
    def session(self) -> AsyncSession:
        if self._session_factory is None:
            raise SessionNotInitializedError()
        stack = self._sessions.get()
        if not stack:
            raise SessionNotInitializedError()
        return stack[-1]

    async def open(self) -> None:
        """Open a new async session on top of the current context's session stack."""
        if self._session_factory is None:
            raise SessionNotInitializedError()
        self._sessions.set((*self._sessions.get(), self._session_factory()))

    async def close(self) -> None:
        """Close the top async session of the current context and return to the one below."""
        if self._session_factory is None:
            return
        stack = self._sessions.get()
        if not stack:
            return
        session = stack[-1]
        self._sessions.set(stack[:-1])
        await session.close()
