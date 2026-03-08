"""Integration tests for spakky-outbox plugin with real PostgreSQL database."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import TypeAdapter
from spakky.core.application.application import SpakkyApplication
from spakky.event.event_publisher import IAsyncEventBus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spakky.plugins.outbox.bus.outbox_event_bus import AsyncOutboxEventBus
from spakky.plugins.outbox.common.config import OutboxConfig
from spakky.plugins.outbox.persistency.table import OutboxMessageTable
from spakky.plugins.outbox.relay.relay import OutboxRelay
from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
)
from spakky.plugins.sqlalchemy.persistency.transaction import AsyncTransaction

from tests.apps.events import OrderConfirmedIntegrationEvent


async def test_async_outbox_event_bus_is_registered_as_primary(
    app: SpakkyApplication,
) -> None:
    """AsyncOutboxEventBus가 @Primary IAsyncEventBus로 컨테이너에 등록되는지 검증한다."""
    bus = app.container.get(IAsyncEventBus)
    assert isinstance(bus, AsyncOutboxEventBus)


async def test_outbox_config_registered_in_container(
    app: SpakkyApplication,
) -> None:
    """OutboxConfig가 컨테이너에 등록되는지 검증한다."""
    config = app.container.get(OutboxConfig)
    assert config is not None
    assert config.batch_size == 100


async def test_send_event_via_outbox_bus_persists_to_db(
    app: SpakkyApplication,
    async_transaction: AsyncTransaction,
    async_connection_manager: AsyncConnectionManager,
) -> None:
    """AsyncOutboxEventBus.send()가 이벤트를 DB에 저장하는지 검증한다."""
    event = OrderConfirmedIntegrationEvent(order_id=uuid4())

    async with async_transaction:
        bus = app.container.get(IAsyncEventBus)
        await bus.send(event)

    async with AsyncSession(async_connection_manager.connection) as session:
        result = await session.execute(
            select(OutboxMessageTable).where(
                OutboxMessageTable.event_name == event.event_name
            )
        )
        messages = result.scalars().all()

    assert len(messages) >= 1
    stored = messages[-1]
    assert stored.event_name == event.event_name
    assert stored.published_at is None
    assert stored.retry_count == 0


async def test_send_event_payload_is_deserializable(
    app: SpakkyApplication,
    async_transaction: AsyncTransaction,
    async_connection_manager: AsyncConnectionManager,
) -> None:
    """저장된 payload가 역직렬화 가능한지 검증한다."""
    original_event = OrderConfirmedIntegrationEvent(order_id=uuid4())

    async with async_transaction:
        bus = app.container.get(IAsyncEventBus)
        await bus.send(original_event)

    async with AsyncSession(async_connection_manager.connection) as session:
        result = await session.execute(
            select(OutboxMessageTable).where(
                OutboxMessageTable.event_name == original_event.event_name
            )
        )
        messages = result.scalars().all()

    stored = messages[-1]
    adapter: TypeAdapter[OrderConfirmedIntegrationEvent] = TypeAdapter(
        OrderConfirmedIntegrationEvent
    )
    recovered = adapter.validate_json(stored.payload)
    assert recovered.order_id == original_event.order_id


async def test_relay_delivers_pending_messages_to_transport(
    app: SpakkyApplication,
    async_transaction: AsyncTransaction,
    async_connection_manager: AsyncConnectionManager,
) -> None:
    """OutboxRelay._relay_batch()가 pending 메시지를 transport로 전달하는지 검증한다."""
    event = OrderConfirmedIntegrationEvent(order_id=uuid4())

    async with async_transaction:
        bus = app.container.get(IAsyncEventBus)
        await bus.send(event)

    mock_transport = MagicMock()
    mock_transport.send = AsyncMock()

    relay = OutboxRelay(
        connection_manager=app.container.get(AsyncConnectionManager),
        transport=mock_transport,
        config=app.container.get(OutboxConfig),
    )

    await relay._relay_batch()

    # Relay delivers all pending messages; verify our event was among them
    mock_transport.send.assert_called()
    sent_order_ids = {
        call.args[0].order_id
        for call in mock_transport.send.call_args_list
        if isinstance(call.args[0], OrderConfirmedIntegrationEvent)
    }
    assert event.order_id in sent_order_ids


async def test_relay_marks_message_as_published(
    app: SpakkyApplication,
    async_transaction: AsyncTransaction,
    async_connection_manager: AsyncConnectionManager,
) -> None:
    """OutboxRelay._relay_batch() 후 메시지 published_at이 설정되는지 검증한다."""
    event = OrderConfirmedIntegrationEvent(order_id=uuid4())

    async with async_transaction:
        bus = app.container.get(IAsyncEventBus)
        await bus.send(event)

    mock_transport = MagicMock()
    mock_transport.send = AsyncMock()

    relay = OutboxRelay(
        connection_manager=app.container.get(AsyncConnectionManager),
        transport=mock_transport,
        config=app.container.get(OutboxConfig),
    )

    await relay._relay_batch()

    async with AsyncSession(async_connection_manager.connection) as session:
        result = await session.execute(
            select(OutboxMessageTable).where(
                OutboxMessageTable.event_name == event.event_name
            )
        )
        messages = result.scalars().all()

    delivered = [m for m in messages if m.published_at is not None]
    assert len(delivered) >= 1


async def test_relay_increments_retry_count_on_transport_failure(
    app: SpakkyApplication,
    async_transaction: AsyncTransaction,
    async_connection_manager: AsyncConnectionManager,
) -> None:
    """전송 실패 시 OutboxRelay가 retry_count를 증가시키는지 검증한다."""
    event = OrderConfirmedIntegrationEvent(order_id=uuid4())

    async with async_transaction:
        bus = app.container.get(IAsyncEventBus)
        await bus.send(event)

    mock_transport = MagicMock()
    mock_transport.send = AsyncMock(side_effect=RuntimeError("broker down"))

    relay = OutboxRelay(
        connection_manager=app.container.get(AsyncConnectionManager),
        transport=mock_transport,
        config=app.container.get(OutboxConfig),
    )

    await relay._relay_batch()

    async with AsyncSession(async_connection_manager.connection) as session:
        result = await session.execute(
            select(OutboxMessageTable).where(
                OutboxMessageTable.event_name == event.event_name
            )
        )
        messages = result.scalars().all()

    retried = [m for m in messages if m.retry_count > 0]
    assert len(retried) >= 1
    assert retried[-1].published_at is None
