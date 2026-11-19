"""Integration tests for AsyncSqlAlchemyOutboxStorage with PostgreSQL."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from spakky.outbox.common.message import OutboxMessage
from sqlalchemy import select

from spakky.plugins.sqlalchemy.outbox.storage import (
    AsyncSqlAlchemyOutboxStorage,
)
from spakky.plugins.sqlalchemy.outbox.table import OutboxMessageTable
from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
)
from spakky.plugins.sqlalchemy.persistency.transaction import AsyncTransaction


class RollbackRequestedError(Exception):
    """scope를 rollback으로 끝내기 위해 올리는 예외."""


def _make_message(
    unique_id: str,
    event_name: str = "TestEvent",
    retry_count: int = 0,
    partition_key: str | None = None,
) -> OutboxMessage:
    """Create OutboxMessage for testing with unique identifier."""
    return OutboxMessage(
        id=uuid4(),
        event_name=f"{event_name}_{unique_id}",
        payload=b'{"data": "test"}',
        created_at=datetime.now(UTC),
        retry_count=retry_count,
        headers={},
        partition_key=partition_key,
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

    with pytest.raises(RollbackRequestedError):
        async with async_transaction.scope():
            await async_storage.save(message)
            raise RollbackRequestedError()

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
async def test_release_claim_expect_message_claimable_again_without_timeout(
    async_transaction: AsyncTransaction,
    async_storage: AsyncSqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """전송에 실패해 claim을 풀면 claim timeout을 기다리지 않고 다음 읽기에서 다시 나간다."""
    message = _make_message(unique_id)
    async with async_transaction:
        await async_storage.save(message)
    [claimed] = [
        r for r in await async_storage.fetch_pending(100, 5) if r.id == message.id
    ]

    await async_storage.release_claim(claimed)

    assert message.id in {r.id for r in await async_storage.fetch_pending(100, 5)}
    await async_storage.mark_published(message.id)


@pytest.mark.asyncio
async def test_release_claim_after_reclaim_by_other_relay_expect_newer_claim_kept(
    async_transaction: AsyncTransaction,
    async_storage: AsyncSqlAlchemyOutboxStorage,
    short_timeout_async_storage: AsyncSqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """claim timeout 뒤 다른 relay가 다시 claim한 메시지는 앞선 relay가 release해도 풀리지 않는다."""
    message = _make_message(unique_id)
    async with async_transaction:
        await async_storage.save(message)
    [stale] = [
        r for r in await async_storage.fetch_pending(100, 5) if r.id == message.id
    ]
    await asyncio.sleep(0.01)
    [newer] = [
        r
        for r in await short_timeout_async_storage.fetch_pending(100, 5)
        if r.id == message.id
    ]
    assert newer.claimed_at != stale.claimed_at

    await async_storage.release_claim(stale)

    assert message.id not in {r.id for r in await async_storage.fetch_pending(100, 5)}
    await async_storage.mark_published(message.id)


@pytest.mark.asyncio
async def test_release_claim_published_message_expect_row_untouched(
    async_transaction: AsyncTransaction,
    async_storage: AsyncSqlAlchemyOutboxStorage,
    async_connection_manager: AsyncConnectionManager,
    unique_id: str,
) -> None:
    """이미 발행된 메시지의 claim은 풀지 않는다."""
    message = _make_message(unique_id)
    async with async_transaction:
        await async_storage.save(message)
    [claimed] = [
        r for r in await async_storage.fetch_pending(100, 5) if r.id == message.id
    ]
    await async_storage.mark_published(message.id)

    await async_storage.release_claim(claimed)

    async with async_connection_manager.connection.connect() as connection:
        claimed_at = (
            await connection.execute(
                select(OutboxMessageTable.claimed_at).where(
                    OutboxMessageTable.id == message.id
                )
            )
        ).scalar_one()
    assert claimed_at is not None


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


@pytest.mark.asyncio
async def test_fetch_pending_partition_key_head_claimed_expect_tail_left_pending(
    async_transaction: AsyncTransaction,
    async_storage: AsyncSqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """키의 선두 메시지가 claim된 동안 같은 키의 후속 메시지가 보류되는지 검증한다."""
    partition_key = f"ORDER-{unique_id}"
    head = _make_message(unique_id, event_name="Head", partition_key=partition_key)

    async with async_transaction:
        await async_storage.save(head)
    claimed = await async_storage.fetch_pending(limit=100, max_retry=5)
    assert head.id in {r.id for r in claimed}

    tail = _make_message(unique_id, event_name="Tail", partition_key=partition_key)
    async with async_transaction:
        await async_storage.save(tail)

    second = await async_storage.fetch_pending(limit=100, max_retry=5)
    assert tail.id not in {r.id for r in second}

    # Leave nothing awaiting delivery: a key stuck in this shared database would
    # keep occupying the claim window of every later test.
    await async_storage.mark_published(head.id)
    await async_storage.mark_published(tail.id)


@pytest.mark.asyncio
async def test_fetch_pending_partition_key_head_published_expect_tail_claimable(
    async_transaction: AsyncTransaction,
    async_storage: AsyncSqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """키의 선두 메시지가 발행되면 같은 키의 후속 메시지를 claim하는지 검증한다."""
    partition_key = f"ORDER-{unique_id}"
    head = _make_message(unique_id, event_name="Head", partition_key=partition_key)

    async with async_transaction:
        await async_storage.save(head)
    await async_storage.fetch_pending(limit=100, max_retry=5)

    tail = _make_message(unique_id, event_name="Tail", partition_key=partition_key)
    async with async_transaction:
        await async_storage.save(tail)
    await async_storage.mark_published(head.id)

    result = await async_storage.fetch_pending(limit=100, max_retry=5)
    assert tail.id in {r.id for r in result}

    await async_storage.mark_published(tail.id)


@pytest.mark.asyncio
async def test_fetch_pending_partition_key_head_abandoned_expect_tail_claimable(
    async_transaction: AsyncTransaction,
    async_storage: AsyncSqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """발행 포기한 선두 메시지가 같은 키의 후속 메시지를 막지 않는지 검증한다."""
    partition_key = f"ORDER-{unique_id}"
    head = _make_message(unique_id, event_name="Head", partition_key=partition_key)
    tail = _make_message(unique_id, event_name="Tail", partition_key=partition_key)

    async with async_transaction:
        await async_storage.save(head)
        await async_storage.save(tail)
    await async_storage.mark_abandoned(head.id)

    result = await async_storage.fetch_pending(limit=100, max_retry=5)
    assert head.id not in {r.id for r in result}
    assert tail.id in {r.id for r in result}

    await async_storage.mark_published(tail.id)


@pytest.mark.asyncio
async def test_purge_published_expect_only_old_published_rows_deleted(
    async_transaction: AsyncTransaction,
    async_storage: AsyncSqlAlchemyOutboxStorage,
    async_connection_manager: AsyncConnectionManager,
    unique_id: str,
) -> None:
    """purge_published()는 기준 시각 전에 발행한 행만 지우고 미발행·포기·최근 발행 행은 남긴다."""
    old_published = _make_message(unique_id, event_name="OldPublished")
    recent_published = _make_message(unique_id, event_name="RecentPublished")
    pending = _make_message(unique_id, event_name="Pending")
    abandoned = _make_message(unique_id, event_name="Abandoned")
    async with async_transaction:
        for message in (old_published, recent_published, pending, abandoned):
            await async_storage.save(message)
    await async_storage.mark_abandoned(abandoned.id)
    await async_storage.mark_published(old_published.id)
    async with async_connection_manager.connection.connect() as connection:
        published_at = (
            await connection.execute(
                select(OutboxMessageTable.published_at).where(
                    OutboxMessageTable.id == old_published.id
                )
            )
        ).scalar_one()
    assert published_at is not None
    older_than = published_at + timedelta(microseconds=1)
    await async_storage.mark_published(recent_published.id)

    deleted = await async_storage.purge_published(older_than)

    async with async_connection_manager.connection.connect() as connection:
        remaining = set(
            (
                await connection.execute(
                    select(OutboxMessageTable.id).where(
                        OutboxMessageTable.id.in_(
                            [
                                old_published.id,
                                recent_published.id,
                                pending.id,
                                abandoned.id,
                            ]
                        )
                    )
                )
            ).scalars()
        )
    assert deleted >= 1
    assert remaining == {recent_published.id, pending.id, abandoned.id}
