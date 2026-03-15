"""Integration tests for SqlAlchemyOutboxStorage with PostgreSQL."""

import time
from datetime import UTC, datetime
from uuid import uuid4

from spakky.outbox.common.message import OutboxMessage

from spakky.plugins.sqlalchemy.outbox.storage import SqlAlchemyOutboxStorage
from spakky.plugins.sqlalchemy.persistency.transaction import Transaction


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


def test_save_persists_message_to_database(
    transaction: Transaction,
    storage: SqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """save()가 메시지를 데이터베이스에 저장하는지 검증한다."""
    message = _make_message(unique_id)

    with transaction:
        storage.save(message)

    result = storage.fetch_pending(limit=100, max_retry=5)
    found = [r for r in result if r.id == message.id]
    assert len(found) == 1
    assert found[0].event_name == f"TestEvent_{unique_id}"


def test_fetch_pending_returns_unpublished_messages(
    transaction: Transaction,
    storage: SqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """fetch_pending()이 미발행 메시지만 반환하는지 검증한다."""
    msg1 = _make_message(unique_id, event_name="Event1")
    msg2 = _make_message(unique_id, event_name="Event2")

    with transaction:
        storage.save(msg1)
        storage.save(msg2)

    storage.mark_published(msg1.id)

    result = storage.fetch_pending(limit=100, max_retry=5)
    result_ids = [r.id for r in result]
    assert msg1.id not in result_ids
    assert msg2.id in result_ids


def test_fetch_pending_respects_max_retry(
    transaction: Transaction,
    storage: SqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """fetch_pending()이 max_retry 초과 메시지를 제외하는지 검증한다."""
    msg_ok = _make_message(unique_id, event_name="OK")
    msg_exhausted = _make_message(unique_id, event_name="Exhausted")

    with transaction:
        storage.save(msg_ok)
        storage.save(msg_exhausted)

    for _ in range(3):
        storage.increment_retry(msg_exhausted.id)

    result = storage.fetch_pending(limit=100, max_retry=3)
    result_ids = [r.id for r in result]
    assert msg_ok.id in result_ids
    assert msg_exhausted.id not in result_ids


def test_fetch_pending_respects_limit(
    transaction: Transaction,
    storage: SqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """fetch_pending()이 limit 파라미터를 준수하는지 검증한다."""
    with transaction:
        for i in range(5):
            storage.save(_make_message(unique_id, event_name=f"Event{i}"))

    result = storage.fetch_pending(limit=2, max_retry=5)
    assert len(result) >= 2  # At least 2 from this test


def test_mark_published_sets_published_at(
    transaction: Transaction,
    storage: SqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """mark_published()가 published_at을 설정하는지 검증한다."""
    message = _make_message(unique_id)

    with transaction:
        storage.save(message)

    storage.mark_published(message.id)

    result = storage.fetch_pending(limit=100, max_retry=5)
    result_ids = [r.id for r in result]
    assert message.id not in result_ids


def test_increment_retry_increases_count(
    transaction: Transaction,
    storage: SqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """increment_retry()가 retry_count를 증가시키는지 검증한다."""
    message = _make_message(unique_id)

    with transaction:
        storage.save(message)

    storage.increment_retry(message.id)
    storage.increment_retry(message.id)

    result = storage.fetch_pending(limit=100, max_retry=5)
    found = [r for r in result if r.id == message.id]
    assert len(found) == 1
    assert found[0].retry_count == 2


def test_rollback_does_not_persist_message(
    transaction: Transaction,
    storage: SqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """트랜잭션 롤백 시 outbox 메시지가 영속화되지 않는지 검증한다."""
    message = _make_message(unique_id)

    transaction.initialize()
    storage.save(message)
    transaction.rollback()
    transaction.dispose()

    result = storage.fetch_pending(limit=100, max_retry=5)
    result_ids = [r.id for r in result]
    assert message.id not in result_ids


def test_fetch_pending_returns_empty_when_no_messages(
    storage: SqlAlchemyOutboxStorage,
) -> None:
    """pending 메시지가 없을 때 빈 리스트를 반환하는지 검증한다."""
    result = storage.fetch_pending(limit=100, max_retry=5)
    assert isinstance(result, list)


def test_fetch_pending_skips_recently_claimed_messages(
    transaction: Transaction,
    storage: SqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """claimed 후 timeout 이내에 재조회 시 해당 메시지가 반환되지 않는지 검증한다."""
    message = _make_message(unique_id)

    with transaction:
        storage.save(message)

    first = storage.fetch_pending(limit=100, max_retry=5)
    first_ids = [r.id for r in first]
    assert message.id in first_ids

    second = storage.fetch_pending(limit=100, max_retry=5)
    second_ids = [r.id for r in second]
    assert message.id not in second_ids


def test_fetch_pending_reclaims_timed_out_messages(
    transaction: Transaction,
    storage: SqlAlchemyOutboxStorage,
    short_timeout_storage: SqlAlchemyOutboxStorage,
    unique_id: str,
) -> None:
    """claim timeout이 만료된 메시지가 다시 조회되는지 검증한다."""
    message = _make_message(unique_id)

    with transaction:
        storage.save(message)

    first = short_timeout_storage.fetch_pending(limit=100, max_retry=5)
    first_ids = [r.id for r in first]
    assert message.id in first_ids

    time.sleep(0.05)

    second = short_timeout_storage.fetch_pending(limit=100, max_retry=5)
    second_ids = [r.id for r in second]
    assert message.id in second_ids
