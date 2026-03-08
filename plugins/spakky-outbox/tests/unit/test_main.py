"""Unit tests for main.py plugin initialization."""

from unittest.mock import MagicMock

from spakky.event.aspects.transactional_event_publishing import (
    AsyncTransactionalEventPublishingAspect,
    TransactionalEventPublishingAspect,
)
from spakky.event.bus.transport_event_bus import DirectEventBus
from spakky.event.mediator.domain_event_mediator import AsyncEventMediator, EventMediator
from spakky.event.post_processor import EventHandlerRegistrationPostProcessor
from spakky.event.publisher.domain_event_publisher import AsyncEventPublisher, EventPublisher

from spakky.plugins.outbox.bus.outbox_event_bus import AsyncOutboxEventBus
from spakky.plugins.outbox.common.config import OutboxConfig
from spakky.plugins.outbox.main import initialize
from spakky.plugins.outbox.relay.relay import OutboxRelay


def test_initialize_expect_all_event_infrastructure_and_outbox_pods_registered() -> None:
    """initialize()가 이벤트 인프라와 Outbox 전용 Pod를 모두 등록하는지 검증한다."""
    mock_app = MagicMock()

    initialize(mock_app)

    added_types = [call.args[0] for call in mock_app.add.call_args_list]

    # Event infrastructure (same as spakky-event, minus AsyncDirectEventBus)
    assert AsyncTransactionalEventPublishingAspect in added_types
    assert TransactionalEventPublishingAspect in added_types
    assert EventMediator in added_types
    assert AsyncEventMediator in added_types
    assert EventPublisher in added_types
    assert AsyncEventPublisher in added_types
    assert DirectEventBus in added_types
    assert EventHandlerRegistrationPostProcessor in added_types

    # Outbox-specific
    assert OutboxConfig in added_types
    assert AsyncOutboxEventBus in added_types
    assert OutboxRelay in added_types
    assert mock_app.add.call_count == 11
