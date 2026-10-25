"""Unit tests for connection managers."""

from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from sqlalchemy import text

import pytest
from sqlalchemy.pool import NullPool

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
    config.async_pool_mode = "queue"
    config.sync_connection_string = None

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
    config.async_pool_mode = "queue"
    config.sync_connection_string = None

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
    config.async_pool_mode = "queue"
    config.sync_connection_string = None

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
    config.async_pool_mode = "queue"
    config.sync_connection_string = None

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
    config.async_pool_mode = "queue"
    config.sync_connection_string = None

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
    config.async_pool_mode = "queue"
    config.sync_connection_string = None

    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()

    with patch(
        "spakky.plugins.sqlalchemy.persistency.connection_manager.create_async_engine",
        return_value=mock_engine,
    ):
        manager = AsyncConnectionManager(config)
        await manager.dispose()

        mock_engine.dispose.assert_awaited_once()


def test_async_connection_manager_null_pool_expect_no_queue_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """여러 event loop용 NullPool은 queue 전용 설정 없이 생성된다."""
    monkeypatch.setenv(
        "SPAKKY_SQLALCHEMY__CONNECTION_STRING", "postgresql+psycopg://localhost/db"
    )
    monkeypatch.setenv("SPAKKY_SQLALCHEMY__ASYNC_POOL_MODE", "null")
    config = SQLAlchemyConnectionConfig()
    with patch(
        "spakky.plugins.sqlalchemy.persistency.connection_manager.create_async_engine"
    ) as create:
        manager = AsyncConnectionManager(config)
        assert manager.connection is create.return_value
        assert create.call_args.kwargs["poolclass"] is NullPool
        assert (
            not {"pool_size", "max_overflow", "pool_timeout"}
            & create.call_args.kwargs.keys()
        )


def test_async_connection_manager_default_pool_expect_existing_queue_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """기본 모드는 기존 bounded queue pool 설정을 유지한다."""
    monkeypatch.setenv(
        "SPAKKY_SQLALCHEMY__CONNECTION_STRING", "postgresql+psycopg://localhost/db"
    )
    monkeypatch.delenv("SPAKKY_SQLALCHEMY__ASYNC_POOL_MODE", raising=False)
    config = SQLAlchemyConnectionConfig()
    with patch(
        "spakky.plugins.sqlalchemy.persistency.connection_manager.create_async_engine"
    ) as create:
        AsyncConnectionManager(config)
        assert config.async_pool_mode == "queue"
        assert create.call_args.kwargs["pool_size"] == config.pool_size
        assert create.call_args.kwargs["max_overflow"] == config.pool_max_overflow
        assert "poolclass" not in create.call_args.kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize("pool_mode", ["queue", "null"])
async def test_async_connection_manager_lifecycle_expect_only_null_pool_warmed(
    monkeypatch: pytest.MonkeyPatch,
    pool_mode: str,
) -> None:
    """NullPool만 시작 때 dialect를 초기화하고 종료 때 dispose한다."""
    from asyncio import Event

    monkeypatch.setenv(
        "SPAKKY_SQLALCHEMY__CONNECTION_STRING", "postgresql+psycopg://localhost/db"
    )
    monkeypatch.setenv("SPAKKY_SQLALCHEMY__ASYNC_POOL_MODE", pool_mode)
    engine = MagicMock()
    engine.dispose = AsyncMock()
    connection = AsyncMock()
    engine.connect.return_value.__aenter__ = AsyncMock(return_value=connection)
    engine.connect.return_value.__aexit__ = AsyncMock()
    with patch(
        "spakky.plugins.sqlalchemy.persistency.connection_manager.create_async_engine",
        return_value=engine,
    ):
        manager = AsyncConnectionManager(SQLAlchemyConnectionConfig())
        manager.set_stop_event(Event())
        await manager.start_async()
        await manager.stop_async()
    if pool_mode == "null":
        connection.execute.assert_awaited_once()
        engine.dispose.assert_awaited_once()
    else:
        engine.connect.assert_not_called()
        engine.dispose.assert_not_awaited()


def test_connection_manager_explicit_sqlite_sync_driver_expect_real_sync_query(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """aiosqlite base URL과 별개로 pysqlite sync URL을 선택해 실제 질의를 수행한다."""
    path = tmp_path / "dual-driver.db"
    monkeypatch.setenv(
        "SPAKKY_SQLALCHEMY__CONNECTION_STRING", f"sqlite+aiosqlite:///{path}"
    )
    monkeypatch.setenv(
        "SPAKKY_SQLALCHEMY__SYNC_CONNECTION_STRING", f"sqlite+pysqlite:///{path}"
    )
    manager = ConnectionManager(SQLAlchemyConnectionConfig())
    try:
        with manager.connection.connect() as connection:
            assert connection.scalar(text("SELECT 1")) == 1
    finally:
        manager.dispose()
