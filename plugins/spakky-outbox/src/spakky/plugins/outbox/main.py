from spakky.core.application.application import SpakkyApplication

from spakky.plugins.outbox.bus.outbox_event_bus import AsyncOutboxEventBus
from spakky.plugins.outbox.common.config import OutboxConfig
from spakky.plugins.outbox.relay.relay import OutboxRelay


def initialize(app: SpakkyApplication) -> None:
    """Initialize the Outbox plugin.

    Registers only the Outbox-specific pods.  ``spakky-event`` must be loaded
    separately (via ``SpakkyApplication.load_plugins``); the outbox plugin builds
    on top of the event infrastructure already registered by that plugin.

    ``AsyncOutboxEventBus`` is decorated with ``@Primary`` so that the DI
    container prefers it over ``AsyncDirectEventBus`` when resolving
    ``IAsyncEventBus`` dependencies.

    Registered pods:
    - OutboxConfig — environment-variable-based configuration.
    - AsyncOutboxEventBus — @Primary IAsyncEventBus, writes events to the Outbox table.
    - OutboxRelay — background service that delivers persisted events via
      IAsyncEventTransport.

    Args:
        app: The Spakky application instance.
    """
    app.add(OutboxConfig)
    app.add(AsyncOutboxEventBus)
    app.add(OutboxRelay)
