"""Unit tests for session managers."""

from unittest.mock import AsyncMock, MagicMock
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
    assert manager._current_session is None


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
    mock_context.get_context_id = lambda: uuid4()

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
    mock_context.get_context_id = lambda: uuid4()

    manager = SessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    manager.open()

    assert manager._current_session is not None
    manager.close()


def test_session_manager_close_removes_session() -> None:
    """close()가 session을 제거하는지 검증한다."""
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = engine

    mock_context = MagicMock()
    mock_context.get_context_id = lambda: uuid4()

    manager = SessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    manager.open()
    manager.close()

    assert manager._current_session is None


def test_session_manager_close_without_open_does_not_raise() -> None:
    """open() 없이 close() 호출해도 에러가 발생하지 않음을 검증한다."""
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = engine

    mock_context = MagicMock()
    mock_context.get_context_id = lambda: uuid4()

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
    mock_context.get_context_id = lambda: uuid4()

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
    assert manager._current_session is None


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
    mock_context.get_context_id = lambda: uuid4()

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
    mock_context.get_context_id = lambda: uuid4()

    manager = AsyncSessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    await manager.open()

    assert manager._current_session is not None
    await manager.close()


@pytest.mark.asyncio
async def test_async_session_manager_close_removes_session() -> None:
    """close()가 session을 제거하는지 검증한다."""
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    mock_context = MagicMock()
    mock_context.get_context_id = lambda: uuid4()

    manager = AsyncSessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    await manager.open()
    await manager.close()

    assert manager._current_session is None


@pytest.mark.asyncio
async def test_async_session_manager_close_without_open_does_not_raise() -> None:
    """open() 없이 close() 호출해도 에러가 발생하지 않음을 검증한다."""
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    mock_context = MagicMock()
    mock_context.get_context_id = lambda: uuid4()

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
    mock_context.get_context_id = lambda: uuid4()

    manager = AsyncSessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    await manager.open()

    # session property를 통해 접근해야 return 라인이 실행됨
    session = manager.session
    assert session is not None
    await manager.close()


@pytest.mark.asyncio
async def test_async_session_manager_close_calls_session_close() -> None:
    """close()가 current_session.close()를 호출하는지 검증한다."""
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_engine = MagicMock()
    mock_connection_manager.connection = mock_engine

    mock_context = MagicMock()
    mock_context.get_context_id = lambda: uuid4()

    manager = AsyncSessionManager(mock_connection_manager)
    manager.set_application_context(mock_context)
    await manager.open()

    # session을 mock으로 교체하여 close 호출 확인
    mock_session = AsyncMock()
    manager._current_session = mock_session

    # scoped_session.remove도 mock 처리
    manager._scoped_session = MagicMock()
    manager._scoped_session.remove = AsyncMock()

    await manager.close()

    mock_session.close.assert_awaited_once()
