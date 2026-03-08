"""Unit tests for AsyncOutboxEventBus."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent

from spakky.plugins.outbox.bus.outbox_event_bus import AsyncOutboxEventBus
from spakky.plugins.outbox.persistency.table import OutboxMessageTable


@immutable
class OrderConfirmedIntegrationEvent(AbstractIntegrationEvent):
    order_id: UUID


@pytest.fixture(name="mock_session")
def mock_session_fixture() -> MagicMock:
    """Create a mock SQLAlchemy AsyncSession."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture(name="mock_session_manager")
def mock_session_manager_fixture(mock_session: MagicMock) -> MagicMock:
    """Create a mock AsyncSessionManager backed by mock_session."""
    manager = MagicMock()
    manager.session = mock_session
    return manager


@pytest.fixture(name="bus")
def bus_fixture(mock_session_manager: MagicMock) -> AsyncOutboxEventBus:
    """Create AsyncOutboxEventBus with mocked session manager."""
    return AsyncOutboxEventBus(session_manager=mock_session_manager)


async def test_send_expect_outbox_message_added_to_session(
    bus: AsyncOutboxEventBus,
    mock_session: MagicMock,
) -> None:
    """send()가 OutboxMessageTable 행을 세션에 추가하는지 검증한다."""
    from uuid import uuid4

    event = OrderConfirmedIntegrationEvent(order_id=uuid4())

    await bus.send(event)

    mock_session.add.assert_called_once()
    added_obj = mock_session.add.call_args[0][0]
    assert isinstance(added_obj, OutboxMessageTable)


async def test_send_expect_event_name_set_correctly(
    bus: AsyncOutboxEventBus,
    mock_session: MagicMock,
) -> None:
    """send()가 event_name 필드를 event.event_name으로 설정하는지 검증한다."""
    from uuid import uuid4

    event = OrderConfirmedIntegrationEvent(order_id=uuid4())

    await bus.send(event)

    added_obj: OutboxMessageTable = mock_session.add.call_args[0][0]
    assert added_obj.event_name == event.event_name


async def test_send_expect_event_type_is_fqcn(
    bus: AsyncOutboxEventBus,
    mock_session: MagicMock,
) -> None:
    """send()가 event_type 필드를 완전한 클래스 경로(FQCN)로 설정하는지 검증한다."""
    from uuid import uuid4

    event = OrderConfirmedIntegrationEvent(order_id=uuid4())
    expected_fqcn = (
        f"{OrderConfirmedIntegrationEvent.__module__}"
        f".{OrderConfirmedIntegrationEvent.__qualname__}"
    )

    await bus.send(event)

    added_obj: OutboxMessageTable = mock_session.add.call_args[0][0]
    assert added_obj.event_type == expected_fqcn


async def test_send_expect_payload_is_json_bytes(
    bus: AsyncOutboxEventBus,
    mock_session: MagicMock,
) -> None:
    """send()가 payload 필드를 JSON bytes로 직렬화하는지 검증한다."""
    from uuid import uuid4

    event = OrderConfirmedIntegrationEvent(order_id=uuid4())

    await bus.send(event)

    added_obj: OutboxMessageTable = mock_session.add.call_args[0][0]
    assert isinstance(added_obj.payload, bytes)
    assert len(added_obj.payload) > 0


async def test_send_expect_session_flush_called(
    bus: AsyncOutboxEventBus,
    mock_session: MagicMock,
) -> None:
    """send()가 세션 flush를 호출하는지 검증한다."""
    from uuid import uuid4

    event = OrderConfirmedIntegrationEvent(order_id=uuid4())

    await bus.send(event)

    mock_session.flush.assert_called_once()
