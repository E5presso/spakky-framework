from spakky.core.application.application import SpakkyApplication
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
from spakky.plugins.outbox.relay.relay import OutboxRelay


def initialize(app: SpakkyApplication) -> None:
    """Initialize the Outbox plugin.

    Registers the full event infrastructure **plus** the Outbox bus, replacing
    ``AsyncDirectEventBus`` with ``AsyncOutboxEventBus`` as the sole
    ``IAsyncEventBus`` implementation.

    This plugin is a **superset** of ``spakky-event``: it provides everything
    the event plugin provides while transparently redirecting integration-event
    publishing to the Outbox table.  Do **not** include ``spakky-event`` in
    ``load_plugins`` alongside this plugin — all event infrastructure is already
    provided here.

    Registered pods:
    - Event infrastructure (same as spakky-event, minus AsyncDirectEventBus)
    - OutboxConfig — environment-variable-based configuration.
    - AsyncOutboxEventBus — sole IAsyncEventBus, writes events to the Outbox table.
    - OutboxRelay — background service that delivers persisted events via
      IAsyncEventTransport.

    Args:
        app: The Spakky application instance.
    """
    # Event infrastructure (mirrors spakky.event.main.initialize except AsyncDirectEventBus)
    app.add(AsyncTransactionalEventPublishingAspect)
    app.add(TransactionalEventPublishingAspect)
    app.add(EventMediator)
    app.add(AsyncEventMediator)
    app.add(EventPublisher)
    app.add(AsyncEventPublisher)
    app.add(DirectEventBus)
    app.add(EventHandlerRegistrationPostProcessor)

    # Outbox-specific pods
    # AsyncOutboxEventBus is the only IAsyncEventBus — no AsyncDirectEventBus registered
    app.add(OutboxConfig)
    app.add(AsyncOutboxEventBus)
    app.add(OutboxRelay)
