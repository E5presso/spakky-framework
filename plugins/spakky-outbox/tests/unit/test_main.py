"""Unit tests for main.py plugin initialization."""

from unittest.mock import MagicMock

from spakky.plugins.outbox.bus.outbox_event_bus import AsyncOutboxEventBus
from spakky.plugins.outbox.common.config import OutboxConfig
from spakky.plugins.outbox.main import initialize
from spakky.plugins.outbox.relay.relay import OutboxRelay


def test_initialize_expect_only_outbox_pods_registered() -> None:
    """initialize()가 Outbox 전용 Pod만 등록하는지 검증한다."""
    mock_app = MagicMock()

    initialize(mock_app)

    added_types = [call.args[0] for call in mock_app.add.call_args_list]

    assert OutboxConfig in added_types
    assert AsyncOutboxEventBus in added_types
    assert OutboxRelay in added_types
    assert mock_app.add.call_count == 3
