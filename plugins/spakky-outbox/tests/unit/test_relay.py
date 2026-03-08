"""Unit tests for OutboxRelay batch logic."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import TypeAdapter
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent

from spakky.plugins.outbox.common.config import OutboxConfig
from spakky.plugins.outbox.persistency.table import OutboxMessageTable
from spakky.plugins.outbox.relay.relay import OutboxRelay


@immutable
class SampleIntegrationEvent(AbstractIntegrationEvent):
    message: str


def _make_relay(
    transport: MagicMock,
    config: OutboxConfig | None = None,
) -> OutboxRelay:
    """Build an OutboxRelay with mocked dependencies."""
    if config is None:
        config = OutboxConfig()

    mock_session_manager = MagicMock()
    mock_session_manager.open = AsyncMock()
    mock_session_manager.close = AsyncMock()

    relay = OutboxRelay(
        session_manager=mock_session_manager,
        transport=transport,
        config=config,
    )
    return relay


def _make_outbox_message(
    event: AbstractIntegrationEvent,
    retry_count: int = 0,
    published_at: datetime | None = None,
) -> OutboxMessageTable:
    """Construct an OutboxMessageTable instance from an event."""
    event_type = type(event)
    fqcn = f"{event_type.__module__}.{event_type.__qualname__}"
    adapter: TypeAdapter[AbstractIntegrationEvent] = TypeAdapter(event_type)
    msg = OutboxMessageTable(
        id=uuid4(),
        event_name=event.event_name,
        event_type=fqcn,
        payload=adapter.dump_json(event),
        retry_count=retry_count,
        published_at=published_at,
    )
    return msg


async def test_relay_batch_expect_published_at_set_on_success() -> None:
    """_relay_batch()가 전송 성공 시 published_at을 현재 시간으로 설정하는지 검증한다."""
    transport = MagicMock()
    transport.send = AsyncMock()
    relay = _make_relay(transport)

    event = SampleIntegrationEvent(message="hello")
    message = _make_outbox_message(event)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [message]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    relay._session_manager.session = mock_session

    await relay._relay_batch()

    transport.send.assert_called_once()
    assert message.published_at is not None


async def test_relay_batch_expect_retry_count_incremented_on_failure() -> None:
    """_relay_batch()가 전송 실패 시 retry_count를 1 증가시키는지 검증한다."""
    transport = MagicMock()
    transport.send = AsyncMock(side_effect=RuntimeError("broker down"))
    relay = _make_relay(transport)

    event = SampleIntegrationEvent(message="hello")
    message = _make_outbox_message(event, retry_count=0)
    original_retry = message.retry_count

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [message]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    relay._session_manager.session = mock_session

    await relay._relay_batch()

    assert message.retry_count == original_retry + 1
    assert message.published_at is None


async def test_relay_batch_expect_session_commit_always_called() -> None:
    """_relay_batch()가 전송 실패에도 session.commit()을 호출하는지 검증한다."""
    transport = MagicMock()
    transport.send = AsyncMock(side_effect=RuntimeError("broker down"))
    relay = _make_relay(transport)

    event = SampleIntegrationEvent(message="hello")
    message = _make_outbox_message(event)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [message]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    relay._session_manager.session = mock_session

    await relay._relay_batch()

    mock_session.commit.assert_called_once()


async def test_relay_batch_expect_session_closed_after_commit() -> None:
    """_relay_batch()가 완료 후 세션 매니저를 닫는지 검증한다."""
    transport = MagicMock()
    transport.send = AsyncMock()
    relay = _make_relay(transport)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    relay._session_manager.session = mock_session

    await relay._relay_batch()

    relay._session_manager.close.assert_called_once()


async def test_relay_initialize_async_expect_no_op() -> None:
    """initialize_async()가 아무 작업도 수행하지 않는지 검증한다."""
    transport = MagicMock()
    relay = _make_relay(transport)

    await relay.initialize_async()  # should not raise or call anything


async def test_relay_dispose_async_expect_no_error() -> None:
    """dispose_async()가 오류 없이 완료되는지 검증한다."""
    transport = MagicMock()
    relay = _make_relay(transport)
    await relay.dispose_async()  # should not raise
