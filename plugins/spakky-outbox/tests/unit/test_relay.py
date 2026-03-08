"""Unit tests for OutboxRelay._import_string helper and relay batch logic."""

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import TypeAdapter
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent

from spakky.plugins.outbox.common.config import OutboxConfig
from spakky.plugins.outbox.persistency.table import OutboxMessageTable
from spakky.plugins.outbox.relay.relay import OutboxRelay, _import_string


@immutable
class SampleIntegrationEvent(AbstractIntegrationEvent):
    message: str


def test_import_string_expect_correct_class_returned() -> None:
    """_import_string이 FQCN으로부터 올바른 클래스를 반환하는지 검증한다."""
    fqcn = (
        f"{SampleIntegrationEvent.__module__}.{SampleIntegrationEvent.__qualname__}"
    )
    result = _import_string(fqcn)
    assert result is SampleIntegrationEvent


def test_import_string_expect_import_error_on_invalid_module() -> None:
    """_import_string이 존재하지 않는 모듈에 대해 ImportError를 발생시키는지 검증한다."""
    with pytest.raises((ImportError, ModuleNotFoundError)):
        _import_string("non.existent.module.SomeClass")


def test_import_string_expect_attribute_error_on_missing_class() -> None:
    """_import_string이 존재하지 않는 클래스에 대해 AttributeError를 발생시키는지 검증한다."""
    with pytest.raises(AttributeError):
        _import_string("spakky.plugins.outbox.relay.relay.NonExistentClass")


def _make_relay(
    transport: MagicMock,
    config: OutboxConfig | None = None,
) -> OutboxRelay:
    """Build an OutboxRelay with mocked dependencies."""
    if config is None:
        config = OutboxConfig()

    mock_engine = MagicMock()
    mock_connection_manager = MagicMock()
    mock_connection_manager.connection = mock_engine

    relay = OutboxRelay(
        connection_manager=mock_connection_manager,
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

    with patch(
        "spakky.plugins.outbox.relay.relay.AsyncSession",
        return_value=mock_session,
    ):
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
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

    with patch(
        "spakky.plugins.outbox.relay.relay.AsyncSession",
        return_value=mock_session,
    ):
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
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

    with patch(
        "spakky.plugins.outbox.relay.relay.AsyncSession",
        return_value=mock_session,
    ):
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        await relay._relay_batch()

    mock_session.commit.assert_called_once()


async def test_relay_initialize_async_expect_create_all_called() -> None:
    """auto_create_table=True일 때 initialize_async()가 테이블을 생성하는지 검증한다."""
    transport = MagicMock()
    relay = _make_relay(transport)

    mock_conn = AsyncMock()
    mock_conn.run_sync = AsyncMock()
    mock_begin = MagicMock()
    mock_begin.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_begin.__aexit__ = AsyncMock(return_value=False)
    relay._engine.begin = MagicMock(return_value=mock_begin)

    await relay.initialize_async()

    mock_conn.run_sync.assert_called_once()


async def test_relay_initialize_async_expect_no_create_when_disabled() -> None:
    """auto_create_table=False일 때 initialize_async()가 테이블을 생성하지 않는지 검증한다."""
    os.environ["SPAKKY_OUTBOX__AUTO_CREATE_TABLE"] = "false"
    try:
        config = OutboxConfig()
        transport = MagicMock()
        relay = _make_relay(transport, config=config)

        relay._engine.begin = MagicMock()

        await relay.initialize_async()

        relay._engine.begin.assert_not_called()
    finally:
        del os.environ["SPAKKY_OUTBOX__AUTO_CREATE_TABLE"]


async def test_relay_dispose_async_expect_no_error() -> None:
    """dispose_async()가 오류 없이 완료되는지 검증한다."""
    transport = MagicMock()
    relay = _make_relay(transport)
    await relay.dispose_async()  # should not raise
