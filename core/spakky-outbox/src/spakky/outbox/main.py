"""Plugin initialization entry point."""

from spakky.core.application.application import SpakkyApplication

from spakky.outbox.bus.outbox_event_bus import (
    AsyncOutboxEventBus,
    OutboxEventBus,
)
from spakky.outbox.common.config import OutboxConfig
from spakky.outbox.relay.relay import (
    AsyncOutboxRelayBackgroundService,
    OutboxRelayBackgroundService,
)


def initialize(app: SpakkyApplication) -> None:
    """Initialize the Outbox plugin.

    Args:
        app: The Spakky application instance.
    """
    app.add(OutboxConfig)
    app.add(OutboxEventBus)
    app.add(AsyncOutboxEventBus)
    app.add(OutboxRelayBackgroundService)
    app.add(AsyncOutboxRelayBackgroundService)
