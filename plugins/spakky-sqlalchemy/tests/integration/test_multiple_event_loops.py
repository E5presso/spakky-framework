"""One native async engine shared by HTTP and background-service event loops."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import text
from sqlalchemy.pool import NullPool

from spakky.plugins.sqlalchemy.common.config import SQLAlchemyConnectionConfig
from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
)


def test_null_pool_concurrent_event_loops_expect_independent_connections(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """실제 PostgreSQL을 두 loop에서 동시에 사용해 queue/connection의 loop 귀속을 막는다."""
    monkeypatch.setenv("SPAKKY_SQLALCHEMY__CONNECTION_STRING", database_url)
    monkeypatch.setenv("SPAKKY_SQLALCHEMY__ASYNC_POOL_MODE", "null")
    # With QueuePool these limits force both loops onto a shared asyncio queue.
    monkeypatch.setenv("SPAKKY_SQLALCHEMY__POOL_SIZE", "1")
    monkeypatch.setenv("SPAKKY_SQLALCHEMY__POOL_MAX_OVERFLOW", "0")
    manager = AsyncConnectionManager(SQLAlchemyConnectionConfig())
    assert isinstance(manager.connection.pool, NullPool)
    asyncio.run(manager.start_async())
    rendezvous = Barrier(2)

    async def query() -> int:
        async with manager.connection.connect() as connection:
            result = await connection.scalar(text("SELECT 1"))
            assert result == 1
            return result

    async def wave() -> list[int]:
        return list(await asyncio.gather(*(query() for _ in range(8))))

    def run_loop() -> list[int]:
        rendezvous.wait(timeout=10)
        return asyncio.run(wave())

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(run_loop)
            second = executor.submit(run_loop)
            assert first.result(timeout=30) == [1] * 8
            assert second.result(timeout=30) == [1] * 8
    finally:
        asyncio.run(manager.stop_async())
