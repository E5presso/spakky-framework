"""Unit tests for session managers."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
    ConnectionManager,
)
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
    SessionNotInitializedError,
)


def test_session_manager_init_stores_engine() -> None:
    """SessionManager가 초기화 시 engine을 저장하는지 검증한다."""
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    manager = SessionManager(mock_connection_manager)

    assert manager._engine is mock_engine
    with pytest.raises(SessionNotInitializedError):
        _ = manager.session


def test_session_manager_session_before_open_raises_error() -> None:
    """open() 전에 session 접근 시 SessionNotInitializedError가 발생함을 검증한다."""
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = MagicMock()

    manager = SessionManager(mock_connection_manager)

    with pytest.raises(SessionNotInitializedError):
        _ = manager.session


def test_session_manager_set_application_context_creates_scoped_session() -> None:
    """set_application_context가 scoped_session을 생성하는지 검증한다."""
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = SessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)

    assert manager._scoped_session is not None


def test_session_manager_open_creates_session() -> None:
    """open()이 session을 생성하는지 검증한다."""
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = SessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    manager.open()

    assert manager.session is not None
    manager.close()


def test_session_manager_close_removes_session() -> None:
    """close()가 session을 제거하는지 검증한다."""
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = SessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    manager.open()
    manager.close()

    with pytest.raises(SessionNotInitializedError):
        _ = manager.session


def test_session_manager_close_without_open_does_not_raise() -> None:
    """open() 없이 close() 호출해도 에러가 발생하지 않음을 검증한다."""
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = SessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    manager.close()  # Should not raise


def test_session_manager_session_property_returns_session() -> None:
    """session property가 Session 객체를 반환하는지 검증한다."""
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = SessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    manager.open()

    from sqlalchemy.orm import Session

    assert isinstance(manager.session, Session)
    manager.close()


# --- Async Session Manager Tests ---


def test_async_session_manager_init_stores_engine() -> None:
    """AsyncSessionManager가 초기화 시 engine을 저장하는지 검증한다."""
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    manager = AsyncSessionManager(mock_connection_manager)

    assert manager._engine is mock_engine
    with pytest.raises(SessionNotInitializedError):
        _ = manager.session


def test_async_session_manager_session_before_open_raises_error() -> None:
    """open() 전에 session 접근 시 SessionNotInitializedError가 발생함을 검증한다."""
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_connection_manager.connection = MagicMock()

    manager = AsyncSessionManager(mock_connection_manager)

    with pytest.raises(SessionNotInitializedError):
        _ = manager.session


def test_async_session_manager_set_application_context_creates_scoped_session() -> None:
    """set_application_context가 async_scoped_session을 생성하는지 검증한다."""
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = AsyncSessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)

    assert manager._scoped_session is not None


@pytest.mark.asyncio
async def test_async_session_manager_open_creates_session() -> None:
    """open()이 session을 생성하는지 검증한다."""
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = AsyncSessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    await manager.open()

    assert manager.session is not None
    await manager.close()


@pytest.mark.asyncio
async def test_async_session_manager_close_removes_session() -> None:
    """close()가 session을 제거하는지 검증한다."""
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = AsyncSessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    await manager.open()
    await manager.close()

    with pytest.raises(SessionNotInitializedError):
        _ = manager.session


@pytest.mark.asyncio
async def test_async_session_manager_close_without_open_does_not_raise() -> None:
    """open() 없이 close() 호출해도 에러가 발생하지 않음을 검증한다."""
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = AsyncSessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    await manager.close()  # Should not raise


@pytest.mark.asyncio
async def test_async_session_manager_session_property_returns_session() -> None:
    """session property가 AsyncSession 객체를 반환하는지 검증한다."""
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    mock_context = MagicMock()
    context_id = uuid4()
    mock_context.get_context_id = lambda: context_id

    manager = AsyncSessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    await manager.open()

    # session property를 통해 접근해야 return 라인이 실행됨
    session = manager.session
    assert session is not None
    await manager.close()


def test_unbound_sync_session_rejects_open_and_accepts_cleanup() -> None:
    """컨텍스트 주입 전에는 열기를 거절하고 정리는 안전하게 끝낸다."""
    manager = SessionManager(MagicMock(spec=ConnectionManager))
    with pytest.raises(SessionNotInitializedError):
        manager.open()
    manager.close()


@pytest.mark.asyncio
async def test_unbound_async_session_rejects_open_and_accepts_cleanup() -> None:
    """비동기 매니저도 컨텍스트 주입 전 자원을 생성하지 않는다."""
    manager = AsyncSessionManager(MagicMock(spec=AsyncConnectionManager))
    with pytest.raises(SessionNotInitializedError):
        await manager.open()
    await manager.close()


def test_shared_sync_manager_keeps_overlapping_contexts_independent() -> None:
    """한 매니저를 공유해도 다른 컨텍스트의 close가 원래 세션을 닫지 않는다."""
    from contextvars import copy_context
    from sqlalchemy import create_engine
    from spakky.core.application.application_context import ApplicationContext

    connection = MagicMock(spec=ConnectionManager)
    connection.connection = create_engine("sqlite:///:memory:")
    manager = SessionManager(connection)
    context = ApplicationContext()
    manager.set_application_context(context)
    manager.open()
    first = manager.session
    other = copy_context()
    other.run(context.clear_context)
    other.run(manager.open)
    assert other.run(lambda: manager.session) is not first
    assert manager.session is first
    other.run(manager.close)
    assert manager.session is first
    manager.close()
    with pytest.raises(SessionNotInitializedError):
        _ = manager.session
    connection.connection.dispose()


@pytest.mark.asyncio
async def test_shared_async_manager_keeps_overlapping_contexts_independent() -> None:
    """비동기 요청 사이에서도 현재 컨텍스트의 세션만 조회·종료한다."""
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine
    from spakky.core.application.application_context import ApplicationContext

    connection = MagicMock(spec=AsyncConnectionManager)
    connection.connection = create_async_engine(
        "postgresql+psycopg://unused:unused@localhost/unused"
    )
    manager = AsyncSessionManager(connection)
    context = ApplicationContext()
    manager.set_application_context(context)
    await manager.open()
    first = manager.session

    async def other_request() -> None:
        context.clear_context()
        await manager.open()
        assert manager.session is not first
        await manager.close()
        with pytest.raises(SessionNotInitializedError):
            _ = manager.session

    await asyncio.create_task(other_request())
    assert manager.session is first
    await manager.close()
    with pytest.raises(SessionNotInitializedError):
        _ = manager.session
    await connection.connection.dispose()
