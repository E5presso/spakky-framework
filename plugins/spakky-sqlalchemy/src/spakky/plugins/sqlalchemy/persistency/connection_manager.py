"""Connection managers for SQLAlchemy engines.

This module provides connection managers that handle SQLAlchemy engine lifecycle,
including proper disposal on application shutdown.
"""

from asyncio import locks
from typing import override

from spakky.core.pod.annotations.pod import Pod
from spakky.core.service.interfaces.service import IAsyncService

from spakky.plugins.sqlalchemy.common.config import SQLAlchemyConnectionConfig
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool


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
            url=config.sync_connection_string or config.connection_string,
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
class AsyncConnectionManager(IAsyncService):
    """Manages asynchronous SQLAlchemy engine lifecycle.

    NullPool mode initializes the dialect before ApplicationContext startup
    completes, so concurrent loops cannot race its first-connect asyncio lock.
    Queue mode retains caller-owned disposal on the loop that owns connections;
    its lifecycle hooks intentionally do not open or dispose connections.
    """

    _connection: AsyncEngine
    _use_null_pool: bool

    @property
    def connection(self) -> AsyncEngine:
        """Get the async SQLAlchemy Engine instance."""
        return self._connection

    def __init__(self, config: SQLAlchemyConnectionConfig) -> None:
        """Create an asynchronous SQLAlchemy engine from configuration."""
        self._use_null_pool = config.async_pool_mode == "null"
        if self._use_null_pool:
            self._connection = create_async_engine(
                url=config.connection_string,
                echo=config.echo,
                echo_pool=config.echo_pool,
                poolclass=NullPool,
                pool_recycle=config.pool_recycle,
                pool_pre_ping=config.pool_pre_ping,
            )
            return
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

    @override
    def set_stop_event(self, stop_event: locks.Event) -> None:
        """No polling loop: lifecycle hooks handle connection initialization."""

    @override
    async def start_async(self) -> None:
        """Initialize NullPool's dialect before multiple loops can use it."""
        if self._use_null_pool:
            async with self._connection.connect() as connection:
                await connection.execute(select(1))

    @override
    async def stop_async(self) -> None:
        """Dispose NullPool; QueuePool remains owned by its requesting loop."""
        if self._use_null_pool:
            await self.dispose()

    async def dispose(self) -> None:
        """Dispose the engine connection pool.

        Must be called from the same event loop where connections were used.
        """
        await self._connection.dispose()
