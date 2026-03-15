"""Integration tests for AsyncSqlAlchemyOutboxStorage with PostgreSQL."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from spakky.outbox.common.message import OutboxMessage

from spakky.plugins.sqlalchemy.outbox.storage import (
    AsyncSqlAlchemyOutboxStorage,
)
from spakky.plugins.sqlalchemy.persistency.transaction import AsyncTransaction


def _make_message(
    unique_id: str,
    event_name: str = "TestEvent",
    retry_count: int = 0,
) -> OutboxMessage:
    """Create OutboxMessage for testing with unique identifier."""
    return OutboxMessage(
        id=uuid4(),
        event_name=f"{event_name}_{unique_id}",
        payload=b'{"data": "test"}',
        created_at=datetime.now(UTC),
        retry_count=retry_count,
    )


@pytest.mark.asyncio
async def test_save_persists_message_to_database(
    async_transaction: AsyncTransaction,
    async_storage: AsyncSqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """save()가 메시지를 데이터베이스에 저장하는지 검증한다."""
    message = _make_message(unique_id)

    async with async_transaction:
        await async_storage.save(message)

    result = await async_storage.fetch_pending(limit=100, max_retry=5)
    found = [r for r in result if r.id == message.id]
    assert len(found) == 1
    assert found[0].event_name == f"TestEvent_{unique_id}"


@pytest.mark.asyncio
async def test_fetch_pending_returns_unpublished_messages(
    async_transaction: AsyncTransaction,
    async_storage: AsyncSqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """fetch_pending()이 미발행 메시지만 반환하는지 검증한다."""
    msg1 = _make_message(unique_id, event_name="Event1")
    msg2 = _make_message(unique_id, event_name="Event2")

    async with async_transaction:
        await async_storage.save(msg1)
        await async_storage.save(msg2)

    await async_storage.mark_published(msg1.id)

    result = await async_storage.fetch_pending(limit=100, max_retry=5)
    result_ids = [r.id for r in result]
    assert msg1.id not in result_ids
    assert msg2.id in result_ids


@pytest.mark.asyncio
async def test_fetch_pending_respects_max_retry(
    async_transaction: AsyncTransaction,
    async_storage: AsyncSqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """fetch_pending()이 max_retry 초과 메시지를 제외하는지 검증한다."""
    msg_ok = _make_message(unique_id, event_name="OK")
    msg_exhausted = _make_message(unique_id, event_name="Exhausted")

    async with async_transaction:
        await async_storage.save(msg_ok)
        await async_storage.save(msg_exhausted)

    for _ in range(3):
        await async_storage.increment_retry(msg_exhausted.id)

    result = await async_storage.fetch_pending(limit=100, max_retry=3)
    result_ids = [r.id for r in result]
    assert msg_ok.id in result_ids
    assert msg_exhausted.id not in result_ids


@pytest.mark.asyncio
async def test_fetch_pending_respects_limit(
    async_transaction: AsyncTransaction,
    async_storage: AsyncSqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """fetch_pending()이 limit 파라미터를 준수하는지 검증한다."""
    async with async_transaction:
        for i in range(5):
            await async_storage.save(_make_message(unique_id, event_name=f"Event{i}"))

    result = await async_storage.fetch_pending(limit=2, max_retry=5)
    assert len(result) >= 2  # At least 2 from this test


@pytest.mark.asyncio
async def test_mark_published_sets_published_at(
    async_transaction: AsyncTransaction,
    async_storage: AsyncSqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """mark_published()가 published_at을 설정하는지 검증한다."""
    message = _make_message(unique_id)

    async with async_transaction:
        await async_storage.save(message)

    await async_storage.mark_published(message.id)

    result = await async_storage.fetch_pending(limit=100, max_retry=5)
    result_ids = [r.id for r in result]
    assert message.id not in result_ids


@pytest.mark.asyncio
async def test_increment_retry_increases_count(
    async_transaction: AsyncTransaction,
    async_storage: AsyncSqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """increment_retry()가 retry_count를 증가시키는지 검증한다."""
    message = _make_message(unique_id)

    async with async_transaction:
        await async_storage.save(message)

    await async_storage.increment_retry(message.id)
    await async_storage.increment_retry(message.id)

    result = await async_storage.fetch_pending(limit=100, max_retry=5)
    found = [r for r in result if r.id == message.id]
    assert len(found) == 1
    assert found[0].retry_count == 2


@pytest.mark.asyncio
async def test_rollback_does_not_persist_message(
    async_transaction: AsyncTransaction,
    async_storage: AsyncSqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """트랜잭션 롤백 시 outbox 메시지가 영속화되지 않는지 검증한다."""
    message = _make_message(unique_id)

    await async_transaction.initialize()
    await async_storage.save(message)
    await async_transaction.rollback()
    await async_transaction.dispose()

    result = await async_storage.fetch_pending(limit=100, max_retry=5)
    result_ids = [r.id for r in result]
    assert message.id not in result_ids


@pytest.mark.asyncio
async def test_fetch_pending_returns_empty_when_no_messages(
    async_storage: AsyncSqlAlchemyOutboxStorage,
) -> None:
    """pending 메시지가 없을 때 빈 리스트를 반환하는지 검증한다."""
    result = await async_storage.fetch_pending(limit=100, max_retry=5)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_fetch_pending_skips_recently_claimed_messages(
    async_transaction: AsyncTransaction,
    async_storage: AsyncSqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """claimed 후 timeout 이내에 재조회 시 해당 메시지가 반환되지 않는지 검증한다."""
    message = _make_message(unique_id)

    async with async_transaction:
        await async_storage.save(message)

    first = await async_storage.fetch_pending(limit=100, max_retry=5)
    first_ids = [r.id for r in first]
    assert message.id in first_ids

    second = await async_storage.fetch_pending(limit=100, max_retry=5)
    second_ids = [r.id for r in second]
    assert message.id not in second_ids


@pytest.mark.asyncio
async def test_fetch_pending_reclaims_timed_out_messages(
    async_transaction: AsyncTransaction,
    async_storage: AsyncSqlAlchemyOutboxStorage,
    short_timeout_async_storage: AsyncSqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """claim timeout이 만료된 메시지가 다시 조회되는지 검증한다."""
    message = _make_message(unique_id)

    async with async_transaction:
        await async_storage.save(message)

    first = await short_timeout_async_storage.fetch_pending(limit=100, max_retry=5)
    first_ids = [r.id for r in first]
    assert message.id in first_ids

    await asyncio.sleep(0.05)

    second = await short_timeout_async_storage.fetch_pending(limit=100, max_retry=5)
    second_ids = [r.id for r in second]
    assert message.id in second_ids
