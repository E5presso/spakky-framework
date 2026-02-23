"""Integration tests for SessionManager and Transaction with real database.

These tests verify the session management and transaction lifecycle using
actual PostgreSQL database via testcontainers.
"""

import pytest
from spakky.core.application.application import SpakkyApplication
from sqlalchemy import text

from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
)
from spakky.plugins.sqlalchemy.persistency.transaction import (
    AsyncTransaction,
    Transaction,
)

# === AsyncSessionManager Integration Tests ===


@pytest.mark.asyncio
async def test_async_session_manager_session_returns_valid_session(
    async_session_manager: AsyncSessionManager,
) -> None:
    """AsyncSessionManager가 유효한 session을 반환하는지 검증한다."""
    session = async_session_manager.session

    assert session is not None


@pytest.mark.asyncio
async def test_async_session_manager_session_returns_same_session_in_same_context(
    async_session_manager: AsyncSessionManager,
) -> None:
    """AsyncSessionManager가 동일 context에서 같은 session을 반환하는지 검증한다."""
    session1 = async_session_manager.session
    session2 = async_session_manager.session

    assert session1 is session2


@pytest.mark.asyncio
async def test_async_session_manager_open_creates_session(
    async_session_manager: AsyncSessionManager,
) -> None:
    """AsyncSessionManager.open()이 session을 생성하는지 검증한다."""
    await async_session_manager.open()

    session = async_session_manager.session
    assert session is not None

    await async_session_manager.close()


@pytest.mark.asyncio
async def test_async_session_manager_close_removes_session(
    async_session_manager: AsyncSessionManager,
) -> None:
    """AsyncSessionManager.close()가 session을 제거하는지 검증한다."""
    await async_session_manager.open()
    session_before = async_session_manager.session

    await async_session_manager.close()

    # close 후 새로운 session이 생성됨
    session_after = async_session_manager.session
    assert session_after is not session_before

    await async_session_manager.close()


@pytest.mark.asyncio
async def test_async_session_manager_executes_query(
    async_session_manager: AsyncSessionManager,
) -> None:
    """AsyncSessionManager로 실제 쿼리를 실행할 수 있는지 검증한다."""
    session = async_session_manager.session

    result = await session.execute(text("SELECT 1 + 1 AS sum"))
    value = result.scalar()

    assert value == 2

    await async_session_manager.close()


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
    async_session_manager: AsyncSessionManager,
    async_transaction: AsyncTransaction,
) -> None:
    """AsyncTransaction context manager가 성공 시 자동 commit하는지 검증한다."""
    async with async_transaction:
        session = async_session_manager.session
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
async def test_async_transaction_executes_insert_and_select(
    app: SpakkyApplication,
    async_session_manager: AsyncSessionManager,
    async_transaction: AsyncTransaction,
) -> None:
    """AsyncTransaction으로 INSERT와 SELECT를 실행할 수 있는지 검증한다."""
    # 임시 테이블 생성 및 데이터 삽입
    async with async_transaction:
        session = async_session_manager.session

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
    new_session_manager: AsyncSessionManager = app.container.get(
        type_=AsyncSessionManager
    )

    async with new_transaction:
        session = new_session_manager.session
        result = await session.execute(
            text("SELECT name FROM test_items WHERE name = :name"),
            {"name": "test_item"},
        )
        row = result.fetchone()

        assert row is not None
        assert row[0] == "test_item"

        # 정리
        await session.execute(text("DROP TABLE IF EXISTS test_items"))


# === SessionManager (Sync) Integration Tests ===


def test_session_manager_session_returns_valid_session(
    session_manager: SessionManager,
) -> None:
    """SessionManager가 유효한 session을 반환하는지 검증한다."""
    session = session_manager.session

    assert session is not None

    session_manager.close()


def test_session_manager_open_and_close_lifecycle(
    session_manager: SessionManager,
) -> None:
    """SessionManager의 open/close 라이프사이클을 검증한다."""
    session_manager.open()
    session_before = session_manager.session

    session_manager.close()

    # close 후 새로운 session이 생성됨
    session_after = session_manager.session
    assert session_after is not session_before

    session_manager.close()


def test_session_manager_executes_query(
    session_manager: SessionManager,
) -> None:
    """SessionManager로 실제 쿼리를 실행할 수 있는지 검증한다."""
    session = session_manager.session

    result = session.execute(text("SELECT 1 + 1 AS sum"))
    value = result.scalar()

    assert value == 2

    session_manager.close()


# === Transaction (Sync) Integration Tests ===


def test_transaction_initialize_and_dispose_lifecycle(
    transaction: Transaction,
) -> None:
    """Transaction의 initialize/dispose 라이프사이클을 검증한다."""
    transaction.initialize()

    # dispose는 예외 없이 실행되어야 함
    transaction.dispose()


def test_transaction_commit_succeeds(
    transaction: Transaction,
) -> None:
    """Transaction.commit()이 정상 동작하는지 검증한다."""
    transaction.initialize()

    # commit은 예외 없이 실행되어야 함
    transaction.commit()

    transaction.dispose()


def test_transaction_rollback_succeeds(
    transaction: Transaction,
) -> None:
    """Transaction.rollback()이 정상 동작하는지 검증한다."""
    transaction.initialize()

    # rollback은 예외 없이 실행되어야 함
    transaction.rollback()

    transaction.dispose()


def test_transaction_context_manager_commits_on_success(
    session_manager: SessionManager,
    transaction: Transaction,
) -> None:
    """Transaction context manager가 성공 시 자동 commit하는지 검증한다."""
    with transaction:
        session = session_manager.session
        result = session.execute(text("SELECT 1"))
        value = result.scalar()
        assert value == 1
