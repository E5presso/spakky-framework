"""Unit tests for SQLAlchemy outbox storage adapters."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from spakky.outbox.common.config import OutboxConfig
from spakky.outbox.common.message import OutboxMessage

from spakky.plugins.sqlalchemy.outbox.storage import (
    AsyncSqlAlchemyOutboxStorage,
    SqlAlchemyOutboxStorage,
)
from spakky.plugins.sqlalchemy.outbox.table import OutboxMessageTable
from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
    ConnectionManager,
)
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
)

# --- Sync storage tests ---


def test_sync_storage_init_without_config_uses_default_timeout() -> None:
    """config 없이 초기화 시 기본 claim_timeout_seconds를 사용하는지 검증한다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = MagicMock()

    storage = SqlAlchemyOutboxStorage(
        mock_session_manager, mock_connection_manager, config=None
    )

    assert storage._claim_timeout_seconds == 300.0


def test_sync_storage_init_with_config_uses_config_timeout() -> None:
    """config가 있을 때 config의 claim_timeout_seconds를 사용하는지 검증한다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = MagicMock()

    config = MagicMock(spec=OutboxConfig)
    config.claim_timeout_seconds = 600.0

    storage = SqlAlchemyOutboxStorage(
        mock_session_manager, mock_connection_manager, config=config
    )

    assert storage._claim_timeout_seconds == 600.0


def test_sync_storage_save_adds_and_flushes_message() -> None:
    """save()가 메시지를 추가하고 flush하는지 검증한다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = MagicMock()
    mock_session = MagicMock()
    mock_session_manager.session = mock_session

    storage = SqlAlchemyOutboxStorage(
        mock_session_manager, mock_connection_manager, config=None
    )

    message = OutboxMessage(
        id=uuid4(),
        event_name="test.event",
        payload=b"test payload",
        headers={},
        created_at=datetime.now(UTC),
    )

    storage.save(message)

    mock_session.add.assert_called_once()
    mock_session.flush.assert_called_once()


def test_sync_storage_fetch_pending_returns_claimed_messages() -> None:
    """fetch_pending()이 메시지를 조회하고 반환하는지 검증한다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = MagicMock()

    storage = SqlAlchemyOutboxStorage(
        mock_session_manager, mock_connection_manager, config=None
    )

    # mock session factory의 결과
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_row = MagicMock(spec=OutboxMessageTable)
    mock_row.id = uuid4()
    mock_row.event_name = "test.event"
    mock_row.payload = b"payload"
    mock_row.headers = {}
    mock_row.created_at = datetime.now(UTC)
    mock_row.published_at = None
    mock_row.retry_count = 0
    mock_row.claimed_at = None
    mock_row.abandoned_at = None
    mock_row.partition_key = None
    mock_result.scalars.return_value.all.return_value = [mock_row]
    mock_session.execute.return_value = mock_result

    # session factory를 mock 처리
    storage._session_factory = MagicMock(return_value=MagicMock())
    storage._session_factory.return_value.__enter__ = MagicMock(
        return_value=mock_session
    )
    storage._session_factory.return_value.__exit__ = MagicMock(return_value=None)

    result = storage.fetch_pending(limit=10, max_retry=3)

    assert len(result) == 1
    assert result[0].event_name == "test.event"
    mock_session.commit.assert_called_once()


def _mock_pending_row(partition_key: str | None) -> MagicMock:
    """Build a pending outbox row stub carrying the given partition key."""
    row = MagicMock(spec=OutboxMessageTable)
    row.id = uuid4()
    row.event_name = "test.event"
    row.payload = b"payload"
    row.headers = {}
    row.created_at = datetime.now(UTC)
    row.published_at = None
    row.retry_count = 0
    row.claimed_at = None
    row.abandoned_at = None
    row.partition_key = partition_key
    return row


def test_sync_storage_fetch_pending_key_headed_elsewhere_expect_not_claimed() -> None:
    """키의 선두 메시지를 다른 릴레이가 잡고 있으면 후속을 claim하지 않는지 검증한다."""
    storage = SqlAlchemyOutboxStorage(
        MagicMock(spec=SessionManager), MagicMock(spec=ConnectionManager), config=None
    )

    tail_row = _mock_pending_row(partition_key="ORD")
    candidates_result = MagicMock()
    candidates_result.scalars.return_value.all.return_value = [tail_row]
    heads_result = MagicMock()
    heads_result.all.return_value = [("ORD", uuid4())]

    mock_session = MagicMock()
    mock_session.execute.side_effect = [candidates_result, heads_result]
    storage._session_factory = MagicMock(return_value=MagicMock())
    storage._session_factory.return_value.__enter__ = MagicMock(
        return_value=mock_session
    )
    storage._session_factory.return_value.__exit__ = MagicMock(return_value=None)

    result = storage.fetch_pending(limit=10, max_retry=3)

    assert result == []
    assert mock_session.execute.call_count == 2
    mock_session.commit.assert_called_once()


def test_sync_storage_fetch_pending_key_head_locked_expect_claimed() -> None:
    """키의 선두 메시지를 직접 잡았으면 그 키의 메시지를 claim하는지 검증한다."""
    storage = SqlAlchemyOutboxStorage(
        MagicMock(spec=SessionManager), MagicMock(spec=ConnectionManager), config=None
    )

    head_row = _mock_pending_row(partition_key="ORD")
    candidates_result = MagicMock()
    candidates_result.scalars.return_value.all.return_value = [head_row]
    heads_result = MagicMock()
    heads_result.all.return_value = [("ORD", head_row.id)]
    claimed_result = MagicMock()
    claimed_result.scalars.return_value.all.return_value = [head_row]

    mock_session = MagicMock()
    mock_session.execute.side_effect = [
        candidates_result,
        heads_result,
        claimed_result,
    ]
    storage._session_factory = MagicMock(return_value=MagicMock())
    storage._session_factory.return_value.__enter__ = MagicMock(
        return_value=mock_session
    )
    storage._session_factory.return_value.__exit__ = MagicMock(return_value=None)

    result = storage.fetch_pending(limit=10, max_retry=3)

    assert [message.id for message in result] == [head_row.id]
    assert result[0].partition_key == "ORD"


def test_sync_storage_mark_published_updates_timestamp() -> None:
    """mark_published()가 published_at을 업데이트하는지 검증한다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = MagicMock()

    storage = SqlAlchemyOutboxStorage(
        mock_session_manager, mock_connection_manager, config=None
    )

    mock_session = MagicMock()
    storage._session_factory = MagicMock(return_value=MagicMock())
    storage._session_factory.return_value.__enter__ = MagicMock(
        return_value=mock_session
    )
    storage._session_factory.return_value.__exit__ = MagicMock(return_value=None)

    message_id = uuid4()
    storage.mark_published(message_id)

    mock_session.execute.assert_called_once()
    mock_session.commit.assert_called_once()


def test_sync_storage_increment_retry_increases_count() -> None:
    """increment_retry()가 retry_count를 증가시키는지 검증한다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = MagicMock()

    storage = SqlAlchemyOutboxStorage(
        mock_session_manager, mock_connection_manager, config=None
    )

    mock_session = MagicMock()
    storage._session_factory = MagicMock(return_value=MagicMock())
    storage._session_factory.return_value.__enter__ = MagicMock(
        return_value=mock_session
    )
    storage._session_factory.return_value.__exit__ = MagicMock(return_value=None)

    message_id = uuid4()
    storage.increment_retry(message_id)

    mock_session.execute.assert_called_once()
    mock_session.commit.assert_called_once()


# --- Async storage tests ---


def test_async_storage_init_without_config_uses_default_timeout() -> None:
    """config 없이 초기화 시 기본 claim_timeout_seconds를 사용하는지 검증한다."""
    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_connection_manager.connection = MagicMock()

    storage = AsyncSqlAlchemyOutboxStorage(
        mock_session_manager, mock_connection_manager, config=None
    )

    assert storage._claim_timeout_seconds == 300.0


def test_async_storage_init_with_config_uses_config_timeout() -> None:
    """config가 있을 때 config의 claim_timeout_seconds를 사용하는지 검증한다."""
    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_connection_manager.connection = MagicMock()

    config = MagicMock(spec=OutboxConfig)
    config.claim_timeout_seconds = 600.0

    storage = AsyncSqlAlchemyOutboxStorage(
        mock_session_manager, mock_connection_manager, config=config
    )

    assert storage._claim_timeout_seconds == 600.0


@pytest.mark.asyncio
async def test_async_storage_save_adds_and_flushes_message() -> None:
    """save()가 메시지를 추가하고 flush하는지 검증한다."""
    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_connection_manager.connection = MagicMock()
    mock_session = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session_manager.session = mock_session

    storage = AsyncSqlAlchemyOutboxStorage(
        mock_session_manager, mock_connection_manager, config=None
    )

    message = OutboxMessage(
        id=uuid4(),
        event_name="test.event",
        payload=b"test payload",
        headers={},
        created_at=datetime.now(UTC),
    )

    await storage.save(message)

    mock_session.add.assert_called_once()
    mock_session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_storage_fetch_pending_returns_claimed_messages() -> None:
    """fetch_pending()이 메시지를 조회하고 반환하는지 검증한다."""
    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_connection_manager.connection = MagicMock()

    storage = AsyncSqlAlchemyOutboxStorage(
        mock_session_manager, mock_connection_manager, config=None
    )

    # mock async session
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_row = MagicMock(spec=OutboxMessageTable)
    mock_row.id = uuid4()
    mock_row.event_name = "test.event"
    mock_row.payload = b"payload"
    mock_row.headers = {}
    mock_row.created_at = datetime.now(UTC)
    mock_row.published_at = None
    mock_row.retry_count = 0
    mock_row.claimed_at = None
    mock_row.abandoned_at = None
    mock_row.partition_key = None
    mock_result.scalars.return_value.all.return_value = [mock_row]
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    # async context manager 설정
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_context.__aexit__ = AsyncMock(return_value=None)
    storage._session_factory = MagicMock(return_value=mock_context)

    result = await storage.fetch_pending(limit=10, max_retry=3)

    assert len(result) == 1
    assert result[0].event_name == "test.event"
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_storage_fetch_pending_key_headed_elsewhere_expect_not_claimed() -> (
    None
):
    """키의 선두 메시지를 다른 릴레이가 잡고 있으면 후속을 claim하지 않는지 검증한다."""
    storage = AsyncSqlAlchemyOutboxStorage(
        MagicMock(spec=AsyncSessionManager),
        MagicMock(spec=AsyncConnectionManager),
        config=None,
    )

    tail_row = _mock_pending_row(partition_key="ORD")
    candidates_result = MagicMock()
    candidates_result.scalars.return_value.all.return_value = [tail_row]
    heads_result = MagicMock()
    heads_result.all.return_value = [("ORD", uuid4())]

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(side_effect=[candidates_result, heads_result])
    mock_session.commit = AsyncMock()
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_context.__aexit__ = AsyncMock(return_value=None)
    storage._session_factory = MagicMock(return_value=mock_context)

    result = await storage.fetch_pending(limit=10, max_retry=3)

    assert result == []
    assert mock_session.execute.await_count == 2
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_storage_fetch_pending_key_head_locked_expect_claimed() -> None:
    """키의 선두 메시지를 직접 잡았으면 그 키의 메시지를 claim하는지 검증한다."""
    storage = AsyncSqlAlchemyOutboxStorage(
        MagicMock(spec=AsyncSessionManager),
        MagicMock(spec=AsyncConnectionManager),
        config=None,
    )

    head_row = _mock_pending_row(partition_key="ORD")
    candidates_result = MagicMock()
    candidates_result.scalars.return_value.all.return_value = [head_row]
    heads_result = MagicMock()
    heads_result.all.return_value = [("ORD", head_row.id)]
    claimed_result = MagicMock()
    claimed_result.scalars.return_value.all.return_value = [head_row]

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(
        side_effect=[candidates_result, heads_result, claimed_result]
    )
    mock_session.commit = AsyncMock()
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_context.__aexit__ = AsyncMock(return_value=None)
    storage._session_factory = MagicMock(return_value=mock_context)

    result = await storage.fetch_pending(limit=10, max_retry=3)

    assert [message.id for message in result] == [head_row.id]
    assert result[0].partition_key == "ORD"


@pytest.mark.asyncio
async def test_async_storage_mark_published_updates_timestamp() -> None:
    """mark_published()가 published_at을 업데이트하는지 검증한다."""
    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_connection_manager.connection = MagicMock()

    storage = AsyncSqlAlchemyOutboxStorage(
        mock_session_manager, mock_connection_manager, config=None
    )

    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_context.__aexit__ = AsyncMock(return_value=None)
    storage._session_factory = MagicMock(return_value=mock_context)

    message_id = uuid4()
    await storage.mark_published(message_id)

    mock_session.execute.assert_awaited_once()
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_storage_increment_retry_increases_count() -> None:
    """increment_retry()가 retry_count를 증가시키는지 검증한다."""
    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_connection_manager.connection = MagicMock()

    storage = AsyncSqlAlchemyOutboxStorage(
        mock_session_manager, mock_connection_manager, config=None
    )

    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_context.__aexit__ = AsyncMock(return_value=None)
    storage._session_factory = MagicMock(return_value=mock_context)

    message_id = uuid4()
    await storage.increment_retry(message_id)

    mock_session.execute.assert_awaited_once()
    mock_session.commit.assert_awaited_once()


# --- partition key round-trip ---


def test_sync_storage_save_writes_partition_key_to_row() -> None:
    """save()가 메시지의 partition_key를 테이블 row에 기록하는지 검증한다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = MagicMock()
    mock_session = MagicMock()
    mock_session_manager.session = mock_session

    storage = SqlAlchemyOutboxStorage(
        mock_session_manager, mock_connection_manager, config=None
    )

    storage.save(
        OutboxMessage(
            id=uuid4(),
            event_name="test.event",
            payload=b"test payload",
            headers={},
            partition_key="ORD-901",
            created_at=datetime.now(UTC),
        )
    )

    assert mock_session.add.call_args.args[0].partition_key == "ORD-901"


def test_sync_storage_fetch_pending_reads_partition_key_from_row() -> None:
    """fetch_pending()이 row의 partition_key를 OutboxMessage로 옮기는지 검증한다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_connection_manager = MagicMock(spec=ConnectionManager)
    mock_connection_manager.connection = MagicMock()

    storage = SqlAlchemyOutboxStorage(
        mock_session_manager, mock_connection_manager, config=None
    )

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_row = MagicMock(spec=OutboxMessageTable)
    mock_row.id = uuid4()
    mock_row.event_name = "test.event"
    mock_row.payload = b"payload"
    mock_row.headers = {}
    mock_row.partition_key = "ORD-902"
    mock_row.created_at = datetime.now(UTC)
    mock_row.published_at = None
    mock_row.retry_count = 0
    mock_row.claimed_at = None
    mock_result.scalars.return_value.all.return_value = [mock_row]
    mock_session.execute.return_value = mock_result

    storage._session_factory = MagicMock(return_value=MagicMock())
    storage._session_factory.return_value.__enter__ = MagicMock(
        return_value=mock_session
    )
    storage._session_factory.return_value.__exit__ = MagicMock(return_value=None)

    result = storage.fetch_pending(limit=10, max_retry=3)

    assert result[0].partition_key == "ORD-902"


@pytest.mark.asyncio
async def test_async_storage_save_writes_partition_key_to_row() -> None:
    """비동기 save()가 메시지의 partition_key를 테이블 row에 기록하는지 검증한다."""
    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_connection_manager.connection = MagicMock()
    mock_session = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session_manager.session = mock_session

    storage = AsyncSqlAlchemyOutboxStorage(
        mock_session_manager, mock_connection_manager, config=None
    )

    await storage.save(
        OutboxMessage(
            id=uuid4(),
            event_name="test.event",
            payload=b"test payload",
            headers={},
            partition_key="ORD-903",
            created_at=datetime.now(UTC),
        )
    )

    assert mock_session.add.call_args.args[0].partition_key == "ORD-903"


@pytest.mark.asyncio
async def test_async_storage_fetch_pending_reads_partition_key_from_row() -> None:
    """비동기 fetch_pending()이 row의 partition_key를 옮기는지 검증한다."""
    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_connection_manager = MagicMock(spec=AsyncConnectionManager)
    mock_connection_manager.connection = MagicMock()

    storage = AsyncSqlAlchemyOutboxStorage(
        mock_session_manager, mock_connection_manager, config=None
    )

    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_row = MagicMock(spec=OutboxMessageTable)
    mock_row.id = uuid4()
    mock_row.event_name = "test.event"
    mock_row.payload = b"payload"
    mock_row.headers = {}
    mock_row.partition_key = "ORD-904"
    mock_row.created_at = datetime.now(UTC)
    mock_row.published_at = None
    mock_row.retry_count = 0
    mock_row.claimed_at = None
    mock_result.scalars.return_value.all.return_value = [mock_row]
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_context.__aexit__ = AsyncMock(return_value=None)
    storage._session_factory = MagicMock(return_value=mock_context)

    result = await storage.fetch_pending(limit=10, max_retry=3)

    assert result[0].partition_key == "ORD-904"


def test_sync_storage_mark_abandoned_updates_timestamp() -> None:
    """mark_abandoned()가 abandoned_at을 기록하는지 검증한다."""
    storage = SqlAlchemyOutboxStorage(
        MagicMock(spec=SessionManager), MagicMock(spec=ConnectionManager), config=None
    )

    mock_session = MagicMock()
    storage._session_factory = MagicMock(return_value=MagicMock())
    storage._session_factory.return_value.__enter__ = MagicMock(
        return_value=mock_session
    )
    storage._session_factory.return_value.__exit__ = MagicMock(return_value=None)

    storage.mark_abandoned(uuid4())

    mock_session.execute.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_async_storage_mark_abandoned_updates_timestamp() -> None:
    """mark_abandoned()가 abandoned_at을 기록하는지 검증한다."""
    storage = AsyncSqlAlchemyOutboxStorage(
        MagicMock(spec=AsyncSessionManager),
        MagicMock(spec=AsyncConnectionManager),
        config=None,
    )

    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_context.__aexit__ = AsyncMock(return_value=None)
    storage._session_factory = MagicMock(return_value=mock_context)

    await storage.mark_abandoned(uuid4())

    mock_session.execute.assert_awaited_once()
    mock_session.commit.assert_awaited_once()
