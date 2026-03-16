"""Unit tests for transaction classes."""

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from spakky.plugins.sqlalchemy.common.config import SQLAlchemyConnectionConfig
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
)
from spakky.plugins.sqlalchemy.persistency.transaction import (
    AsyncTransaction,
    Transaction,
)


def test_transaction_init_stores_session_manager() -> None:
    """Transaction이 session_manager를 저장하는지 검증한다."""
    mock_config = MagicMock(spec=SQLAlchemyConnectionConfig)
    mock_config.autocommit = True
    mock_session_manager = MagicMock(spec=SessionManager)

    tx = Transaction(mock_config, mock_session_manager)

    assert tx._session_manager is mock_session_manager


def test_transaction_session_property_returns_session() -> None:
    """session property가 session을 반환하는지 검증한다."""
    mock_config = MagicMock(spec=SQLAlchemyConnectionConfig)
    mock_config.autocommit = True
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    tx = Transaction(mock_config, mock_session_manager)

    assert tx.session is mock_session


def test_transaction_initialize_calls_open() -> None:
    """initialize가 session_manager.open()을 호출하는지 검증한다."""
    mock_config = MagicMock(spec=SQLAlchemyConnectionConfig)
    mock_config.autocommit = True
    mock_session_manager = MagicMock(spec=SessionManager)

    tx = Transaction(mock_config, mock_session_manager)
    tx.initialize()

    mock_session_manager.open.assert_called_once()


def test_transaction_dispose_calls_close() -> None:
    """dispose가 session_manager.close()를 호출하는지 검증한다."""
    mock_config = MagicMock(spec=SQLAlchemyConnectionConfig)
    mock_config.autocommit = True
    mock_session_manager = MagicMock(spec=SessionManager)

    tx = Transaction(mock_config, mock_session_manager)
    tx.dispose()

    mock_session_manager.close.assert_called_once()


def test_transaction_commit_calls_session_commit() -> None:
    """commit이 session.commit()을 호출하는지 검증한다."""
    mock_config = MagicMock(spec=SQLAlchemyConnectionConfig)
    mock_config.autocommit = True
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    tx = Transaction(mock_config, mock_session_manager)
    tx.commit()

    mock_session.commit.assert_called_once()


def test_transaction_rollback_calls_session_rollback() -> None:
    """rollback이 session.rollback()을 호출하는지 검증한다."""
    mock_config = MagicMock(spec=SQLAlchemyConnectionConfig)
    mock_config.autocommit = True
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    tx = Transaction(mock_config, mock_session_manager)
    tx.rollback()

    mock_session.rollback.assert_called_once()


# --- Async Transaction Tests ---


def test_async_transaction_init_stores_session_manager() -> None:
    """AsyncTransaction이 session_manager를 저장하는지 검증한다."""
    mock_config = MagicMock(spec=SQLAlchemyConnectionConfig)
    mock_config.autocommit = True
    mock_session_manager = MagicMock(spec=AsyncSessionManager)

    tx = AsyncTransaction(mock_config, mock_session_manager)

    assert tx._session_manager is mock_session_manager


def test_async_transaction_session_property_returns_session() -> None:
    """session property가 session을 반환하는지 검증한다."""
    mock_config = MagicMock(spec=SQLAlchemyConnectionConfig)
    mock_config.autocommit = True
    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    tx = AsyncTransaction(mock_config, mock_session_manager)

    assert tx.session is mock_session


@pytest.mark.asyncio
async def test_async_transaction_initialize_calls_open() -> None:
    """initialize가 session_manager.open()을 호출하는지 검증한다."""
    mock_config = MagicMock(spec=SQLAlchemyConnectionConfig)
    mock_config.autocommit = True
    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_session_manager.open = AsyncMock()

    tx = AsyncTransaction(mock_config, mock_session_manager)
    await tx.initialize()

    mock_session_manager.open.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_transaction_dispose_calls_close() -> None:
    """dispose가 session_manager.close()를 호출하는지 검증한다."""
    mock_config = MagicMock(spec=SQLAlchemyConnectionConfig)
    mock_config.autocommit = True
    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_session_manager.close = AsyncMock()

    tx = AsyncTransaction(mock_config, mock_session_manager)
    await tx.dispose()

    mock_session_manager.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_transaction_commit_calls_session_commit() -> None:
    """commit이 session.commit()을 호출하는지 검증한다."""
    mock_config = MagicMock(spec=SQLAlchemyConnectionConfig)
    mock_config.autocommit = True
    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_session = AsyncMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    tx = AsyncTransaction(mock_config, mock_session_manager)
    await tx.commit()

    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_transaction_rollback_calls_session_rollback() -> None:
    """rollback이 session.rollback()을 호출하는지 검증한다."""
    mock_config = MagicMock(spec=SQLAlchemyConnectionConfig)
    mock_config.autocommit = True
    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_session = AsyncMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    tx = AsyncTransaction(mock_config, mock_session_manager)
    await tx.rollback()

    mock_session.rollback.assert_awaited_once()
