"""Unit tests for connection managers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from spakky.plugins.sqlalchemy.common.config import SQLAlchemyConnectionConfig
from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
    ConnectionManager,
)


def test_connection_manager_init_creates_engine() -> None:
    """ConnectionManager가 엔진을 올바르게 생성하는지 검증한다."""
    config = MagicMock(spec=SQLAlchemyConnectionConfig)
    config.connection_string = "sqlite:///:memory:"
    config.echo = False
    config.echo_pool = False
    config.pool_size = 5
    config.pool_max_overflow = 10
    config.pool_timeout = 30
    config.pool_recycle = 3600
    config.pool_pre_ping = True

    mock_engine = MagicMock()

    with patch(
        "spakky.plugins.sqlalchemy.persistency.connection_manager.create_engine",
        return_value=mock_engine,
    ) as mock_create:
        manager = ConnectionManager(config)

        mock_create.assert_called_once()
        assert manager.connection is mock_engine


def test_connection_manager_connection_property_returns_engine() -> None:
    """connection property가 Engine을 반환하는지 검증한다."""
    config = MagicMock(spec=SQLAlchemyConnectionConfig)
    config.connection_string = "sqlite:///:memory:"
    config.echo = False
    config.echo_pool = False
    config.pool_size = 5
    config.pool_max_overflow = 10
    config.pool_timeout = 30
    config.pool_recycle = 3600
    config.pool_pre_ping = True

    mock_engine = MagicMock()

    with patch(
        "spakky.plugins.sqlalchemy.persistency.connection_manager.create_engine",
        return_value=mock_engine,
    ):
        manager = ConnectionManager(config)

        assert manager.connection is mock_engine


def test_connection_manager_dispose_disposes_engine() -> None:
    """dispose가 엔진을 정리하는지 검증한다."""
    config = MagicMock(spec=SQLAlchemyConnectionConfig)
    config.connection_string = "sqlite:///:memory:"
    config.echo = False
    config.echo_pool = False
    config.pool_size = 5
    config.pool_max_overflow = 10
    config.pool_timeout = 30
    config.pool_recycle = 3600
    config.pool_pre_ping = True

    mock_engine = MagicMock()

    with patch(
        "spakky.plugins.sqlalchemy.persistency.connection_manager.create_engine",
        return_value=mock_engine,
    ):
        manager = ConnectionManager(config)
        manager.dispose()

        mock_engine.dispose.assert_called_once()


def test_async_connection_manager_init_creates_async_engine() -> None:
    """AsyncConnectionManager가 async 엔진을 올바르게 생성하는지 검증한다."""
    config = MagicMock(spec=SQLAlchemyConnectionConfig)
    config.connection_string = "sqlite+aiosqlite:///:memory:"
    config.echo = False
    config.echo_pool = False
    config.pool_size = 5
    config.pool_max_overflow = 10
    config.pool_timeout = 30
    config.pool_recycle = 3600
    config.pool_pre_ping = True

    mock_engine = MagicMock()

    with patch(
        "spakky.plugins.sqlalchemy.persistency.connection_manager.create_async_engine",
        return_value=mock_engine,
    ) as mock_create:
        manager = AsyncConnectionManager(config)

        mock_create.assert_called_once()
        assert manager.connection is mock_engine


def test_async_connection_manager_connection_property_returns_async_engine() -> None:
    """connection property가 AsyncEngine을 반환하는지 검증한다."""
    config = MagicMock(spec=SQLAlchemyConnectionConfig)
    config.connection_string = "sqlite+aiosqlite:///:memory:"
    config.echo = False
    config.echo_pool = False
    config.pool_size = 5
    config.pool_max_overflow = 10
    config.pool_timeout = 30
    config.pool_recycle = 3600
    config.pool_pre_ping = True

    mock_engine = MagicMock()

    with patch(
        "spakky.plugins.sqlalchemy.persistency.connection_manager.create_async_engine",
        return_value=mock_engine,
    ):
        manager = AsyncConnectionManager(config)

        assert manager.connection is mock_engine


@pytest.mark.asyncio
async def test_async_connection_manager_dispose_disposes_engine() -> None:
    """async dispose가 엔진을 정리하는지 검증한다."""
    config = MagicMock(spec=SQLAlchemyConnectionConfig)
    config.connection_string = "sqlite+aiosqlite:///:memory:"
    config.echo = False
    config.echo_pool = False
    config.pool_size = 5
    config.pool_max_overflow = 10
    config.pool_timeout = 30
    config.pool_recycle = 3600
    config.pool_pre_ping = True

    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()

    with patch(
        "spakky.plugins.sqlalchemy.persistency.connection_manager.create_async_engine",
        return_value=mock_engine,
    ):
        manager = AsyncConnectionManager(config)
        await manager.dispose()

        mock_engine.dispose.assert_awaited_once()
