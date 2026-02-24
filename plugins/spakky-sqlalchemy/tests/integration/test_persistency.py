"""Integration tests for SessionManager and Transaction with real database.

These tests verify the session management and transaction lifecycle using
actual PostgreSQL database via testcontainers.
"""

import pytest
from spakky.core.application.application import SpakkyApplication
from sqlalchemy import text

from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionNotInitializedError,
)
from spakky.plugins.sqlalchemy.persistency.transaction import AsyncTransaction

# === SessionManager Error Tests ===


@pytest.mark.asyncio
async def test_async_session_manager_access_without_open_expect_error(
    app: SpakkyApplication,
) -> None:
    """AsyncSessionManager가 open() 없이 session 접근 시 에러를 발생시키는지 검증한다."""
    session_manager: AsyncSessionManager = app.container.get(type_=AsyncSessionManager)

    with pytest.raises(SessionNotInitializedError):
        _ = session_manager.session


@pytest.mark.asyncio
async def test_async_session_manager_open_creates_session(
    app: SpakkyApplication,
) -> None:
    """AsyncSessionManager.open()이 session을 생성하는지 검증한다."""
    session_manager: AsyncSessionManager = app.container.get(type_=AsyncSessionManager)

    await session_manager.open()

    session = session_manager.session
    assert session is not None

    await session_manager.close()


@pytest.mark.asyncio
async def test_async_session_manager_close_invalidates_session(
    app: SpakkyApplication,
) -> None:
    """AsyncSessionManager.close() 후 session 접근 시 에러를 발생시키는지 검증한다."""
    session_manager: AsyncSessionManager = app.container.get(type_=AsyncSessionManager)

    await session_manager.open()
    await session_manager.close()

    with pytest.raises(SessionNotInitializedError):
        _ = session_manager.session


# === AsyncTransaction Integration Tests ===


@pytest.mark.asyncio
async def test_async_transaction_autocommit_enabled_by_default(
    async_transaction: AsyncTransaction,
) -> None:
    """AsyncTransaction이 기본적으로 autocommit=True인지 검증한다."""
    assert async_transaction.autocommit_enabled is True


@pytest.mark.asyncio
async def test_async_transaction_initialize_and_dispose_lifecycle(
    async_transaction: AsyncTransaction,
) -> None:
    """AsyncTransaction의 initialize/dispose 라이프사이클을 검증한다."""
    await async_transaction.initialize()

    # dispose는 예외 없이 실행되어야 함
    await async_transaction.dispose()


@pytest.mark.asyncio
async def test_async_transaction_session_access_after_initialize(
    async_transaction: AsyncTransaction,
) -> None:
    """AsyncTransaction.initialize() 후 session 접근이 가능한지 검증한다."""
    await async_transaction.initialize()

    session = async_transaction.session
    assert session is not None

    await async_transaction.dispose()


@pytest.mark.asyncio
async def test_async_transaction_session_access_in_context_manager(
    async_transaction: AsyncTransaction,
) -> None:
    """AsyncTransaction context manager 내에서 session 접근이 가능한지 검증한다."""
    async with async_transaction:
        session = async_transaction.session
        assert session is not None


@pytest.mark.asyncio
async def test_async_transaction_commit_succeeds(
    async_transaction: AsyncTransaction,
) -> None:
    """AsyncTransaction.commit()이 정상 동작하는지 검증한다."""
    await async_transaction.initialize()

    # commit은 예외 없이 실행되어야 함
    await async_transaction.commit()

    await async_transaction.dispose()


@pytest.mark.asyncio
async def test_async_transaction_rollback_succeeds(
    async_transaction: AsyncTransaction,
) -> None:
    """AsyncTransaction.rollback()이 정상 동작하는지 검증한다."""
    await async_transaction.initialize()

    # rollback은 예외 없이 실행되어야 함
    await async_transaction.rollback()

    await async_transaction.dispose()


@pytest.mark.asyncio
async def test_async_transaction_context_manager_commits_on_success(
    async_transaction: AsyncTransaction,
) -> None:
    """AsyncTransaction context manager가 성공 시 자동 commit하는지 검증한다."""
    async with async_transaction:
        session = async_transaction.session
        result = await session.execute(text("SELECT 1"))
        value = result.scalar()
        assert value == 1


@pytest.mark.asyncio
async def test_async_transaction_context_manager_rollbacks_on_exception(
    async_transaction: AsyncTransaction,
) -> None:
    """AsyncTransaction context manager가 예외 발생 시 rollback하는지 검증한다."""
    with pytest.raises(ValueError, match="Test exception"):
        async with async_transaction:
            raise ValueError("Test exception")


@pytest.mark.asyncio
async def test_async_transaction_executes_query(
    async_transaction: AsyncTransaction,
) -> None:
    """AsyncTransaction으로 실제 쿼리를 실행할 수 있는지 검증한다."""
    async with async_transaction:
        session = async_transaction.session
        result = await session.execute(text("SELECT 1 + 1 AS sum"))
        value = result.scalar()

        assert value == 2


@pytest.mark.asyncio
async def test_async_transaction_executes_insert_and_select(
    app: SpakkyApplication,
    async_transaction: AsyncTransaction,
) -> None:
    """AsyncTransaction으로 INSERT와 SELECT를 실행할 수 있는지 검증한다."""
    # 임시 테이블 생성 및 데이터 삽입
    async with async_transaction:
        session = async_transaction.session

        # 임시 테이블 생성
        await session.execute(
            text(
                "CREATE TEMP TABLE IF NOT EXISTS test_items "
                "(id SERIAL PRIMARY KEY, name VARCHAR(100))"
            )
        )

        # 데이터 삽입
        await session.execute(
            text("INSERT INTO test_items (name) VALUES (:name)"),
            {"name": "test_item"},
        )

    # 새 transaction에서 조회
    new_transaction: AsyncTransaction = app.container.get(type_=AsyncTransaction)

    async with new_transaction:
        session = new_transaction.session
        result = await session.execute(
            text("SELECT name FROM test_items WHERE name = :name"),
            {"name": "test_item"},
        )
        row = result.fetchone()

        assert row is not None
        assert row[0] == "test_item"

        # 정리
        await session.execute(text("DROP TABLE IF EXISTS test_items"))
