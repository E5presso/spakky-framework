"""Connection managers for SQLAlchemy engines.

This module provides connection managers that handle SQLAlchemy engine lifecycle,
including proper disposal on application shutdown.
"""

from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.sqlalchemy.common.config import SQLAlchemyConnectionConfig
from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


@Pod()
class ConnectionManager:
    """Manages synchronous SQLAlchemy engine lifecycle."""

    _connection: Engine

    @property
    def connection(self) -> Engine:
        """Get the SQLAlchemy Engine instance."""
        return self._connection

    def __init__(self, config: SQLAlchemyConnectionConfig) -> None:
        """Create a synchronous SQLAlchemy engine from configuration."""
        self._connection = create_engine(
            url=config.connection_string,
            echo=config.echo,
            echo_pool=config.echo_pool,
            pool_size=config.pool_size,
            max_overflow=config.pool_max_overflow,
            pool_timeout=config.pool_timeout,
            pool_recycle=config.pool_recycle,
            pool_pre_ping=config.pool_pre_ping,
        )

    def dispose(self) -> None:
        """Dispose the engine connection pool."""
        self._connection.dispose()


@Pod()
class AsyncConnectionManager:
    """Manages asynchronous SQLAlchemy engine lifecycle.

    Note: Does not implement IAsyncService because AsyncEngine.dispose() must be
    called from the same event loop where connections were created. In test
    environments with pytest-asyncio, this means dispose must be called from
    the test's event loop, not ApplicationContext's internal event loop thread.
    """

    _connection: AsyncEngine

    @property
    def connection(self) -> AsyncEngine:
        """Get the async SQLAlchemy Engine instance."""
        return self._connection

    def __init__(self, config: SQLAlchemyConnectionConfig) -> None:
        """Create an asynchronous SQLAlchemy engine from configuration."""
        self._connection = create_async_engine(
            url=config.connection_string,
            echo=config.echo,
            echo_pool=config.echo_pool,
            pool_size=config.pool_size,
            max_overflow=config.pool_max_overflow,
            pool_timeout=config.pool_timeout,
            pool_recycle=config.pool_recycle,
            pool_pre_ping=config.pool_pre_ping,
        )

    async def dispose(self) -> None:
        """Dispose the engine connection pool.

        Must be called from the same event loop where connections were used.
        """
        await self._connection.dispose()
