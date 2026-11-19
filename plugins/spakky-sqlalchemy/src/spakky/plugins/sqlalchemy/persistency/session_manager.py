from contextvars import ContextVar
from dataclasses import dataclass

from spakky.core.pod.annotations.pod import Pod
from spakky.data.persistency.error import TransactionAlreadyFinishedError
from spakky.data.persistency.transaction import PhysicalTransaction
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


class SessionNotBoundError(AbstractSpakkySqlAlchemyPersistencyError):
    """Raised when a joined transaction has no session in the current context.

    Every physical transaction opened through ``open()`` keeps its session on
    the context's stack, and a context that joins it inherited that stack. A
    missing session means ``join()`` was called for a transaction this session
    manager never opened.
    """

    message = "No session is bound to the joined transaction in this context."


@dataclass(eq=False, slots=True)
class SessionSlot[S: (Session, AsyncSession)]:
    """The session of one physical transaction.

    The slot is bound to the physical transaction that owns the session. The
    transaction object is shared by every execution context that copied the
    session stack, so the moment it finishes is seen at once by child tasks
    and threads that still hold the slot.
    """

    session: S
    """The session of the physical transaction."""

    transaction: PhysicalTransaction
    """The physical transaction this session belongs to."""


@Pod()
class SessionManager(IApplicationContextAware):
    """Manages synchronous SQLAlchemy sessions per execution context.

    Each execution context keeps a stack of session slots that mirrors its
    transaction scopes. ``open()`` pushes a new session bound to a new
    physical transaction (the outermost scope or ``Propagation.REQUIRES_NEW``)
    and ``close()`` pops and closes it. ``join()`` pushes the slot of the
    transaction a ``Propagation.REQUIRED`` scope joined and ``leave()`` pops
    it. ``session`` is the session of the top slot, that is, of the physical
    transaction the current scope belongs to.

    The stack is an immutable tuple held in a ``ContextVar``. A child task or
    thread that copied the execution context starts from the parent's stack,
    so it sees the parent's session, but the sessions it opens and closes stay
    in its own context and never replace the session another task is using.
    Once the transaction of the top slot has finished, ``session`` raises
    ``TransactionAlreadyFinishedError`` instead of handing out the session
    below it: a write never lands in a transaction other than the one its
    scope belongs to.
    """

    _application_context: IApplicationContext
    _engine: Engine
    _session_factory: sessionmaker[Session] | None
    _sessions: ContextVar[tuple[SessionSlot[Session], ...]]

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
        """The session of the physical transaction the current scope belongs to.

        Raises:
            SessionNotInitializedError: No session is open in this context.
            TransactionAlreadyFinishedError: That transaction has already
                committed or rolled back.
        """
        stack = self._sessions.get()
        if self._session_factory is None or not stack:
            raise SessionNotInitializedError()
        if stack[-1].transaction.finished:
            raise TransactionAlreadyFinishedError()
        return stack[-1].session

    def open(self, transaction: PhysicalTransaction) -> None:
        """Open a new session for a new physical transaction.

        Args:
            transaction: The physical transaction the session belongs to.
        """
        if self._session_factory is None:
            raise SessionNotInitializedError()
        self._sessions.set(
            (*self._sessions.get(), SessionSlot(self._session_factory(), transaction))
        )

    def join(self, transaction: PhysicalTransaction) -> None:
        """Use the session of a transaction a scope joined in this context.

        Args:
            transaction: The physical transaction joined by the scope.

        Raises:
            SessionNotBoundError: This context holds no session of it.
        """
        stack = self._sessions.get()
        for slot in reversed(stack):
            if slot.transaction is transaction:
                self._sessions.set((*stack, slot))
                return
        raise SessionNotBoundError()

    def leave(self) -> None:
        """Stop using the session pushed by ``join()``.

        Raises:
            SessionNotInitializedError: No session is open in this context.
        """
        stack = self._sessions.get()
        if not stack:
            raise SessionNotInitializedError()
        self._sessions.set(stack[:-1])

    def close(self) -> None:
        """Close the top session of the current context and return to the one below."""
        if self._session_factory is None:
            return
        stack = self._sessions.get()
        if not stack:
            return
        self._sessions.set(stack[:-1])
        stack[-1].session.close()


@Pod()
class AsyncSessionManager(IApplicationContextAware):
    """Manages asynchronous SQLAlchemy sessions per execution context.

    Each execution context keeps a stack of session slots that mirrors its
    transaction scopes. ``open()`` pushes a new session bound to a new
    physical transaction (the outermost scope or ``Propagation.REQUIRES_NEW``)
    and ``close()`` pops and closes it. ``join()`` pushes the slot of the
    transaction a ``Propagation.REQUIRED`` scope joined and ``leave()`` pops
    it. ``session`` is the session of the top slot, that is, of the physical
    transaction the current scope belongs to.

    The stack is an immutable tuple held in a ``ContextVar``. A child task or
    thread that copied the execution context starts from the parent's stack,
    so it sees the parent's session, but the sessions it opens and closes stay
    in its own context and never replace the session another task is using.
    Once the transaction of the top slot has finished, ``session`` raises
    ``TransactionAlreadyFinishedError`` instead of handing out the session
    below it: a write never lands in a transaction other than the one its
    scope belongs to.
    """

    _application_context: IApplicationContext
    _engine: AsyncEngine
    _session_factory: async_sessionmaker[AsyncSession] | None
    _sessions: ContextVar[tuple[SessionSlot[AsyncSession], ...]]

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
        """The session of the physical transaction the current scope belongs to.

        Raises:
            SessionNotInitializedError: No session is open in this context.
            TransactionAlreadyFinishedError: That transaction has already
                committed or rolled back.
        """
        stack = self._sessions.get()
        if self._session_factory is None or not stack:
            raise SessionNotInitializedError()
        if stack[-1].transaction.finished:
            raise TransactionAlreadyFinishedError()
        return stack[-1].session

    async def open(self, transaction: PhysicalTransaction) -> None:
        """Open a new async session for a new physical transaction.

        Args:
            transaction: The physical transaction the session belongs to.
        """
        if self._session_factory is None:
            raise SessionNotInitializedError()
        self._sessions.set(
            (*self._sessions.get(), SessionSlot(self._session_factory(), transaction))
        )

    async def join(self, transaction: PhysicalTransaction) -> None:
        """Use the session of a transaction a scope joined in this context.

        Args:
            transaction: The physical transaction joined by the scope.

        Raises:
            SessionNotBoundError: This context holds no session of it.
        """
        stack = self._sessions.get()
        for slot in reversed(stack):
            if slot.transaction is transaction:
                self._sessions.set((*stack, slot))
                return
        raise SessionNotBoundError()

    async def leave(self) -> None:
        """Stop using the session pushed by ``join()``.

        Raises:
            SessionNotInitializedError: No session is open in this context.
        """
        stack = self._sessions.get()
        if not stack:
            raise SessionNotInitializedError()
        self._sessions.set(stack[:-1])

    async def close(self) -> None:
        """Close the top async session of the current context and return to the one below."""
        if self._session_factory is None:
            return
        stack = self._sessions.get()
        if not stack:
            return
        self._sessions.set(stack[:-1])
        await stack[-1].session.close()
