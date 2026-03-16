from spakky.core.application.application import SpakkyApplication

from spakky.event.aspects.transactional_event_publishing import (
    AsyncTransactionalEventPublishingAspect,
    TransactionalEventPublishingAspect,
)
from spakky.event.bus.transport_event_bus import (
    AsyncDirectEventBus,
    DirectEventBus,
)
from spakky.event.mediator.domain_event_mediator import (
    AsyncEventMediator,
    EventMediator,
)
from spakky.event.post_processor import EventHandlerRegistrationPostProcessor
from spakky.event.publisher.domain_event_publisher import (
    AsyncEventPublisher,
    EventPublisher,
)


def initialize(app: SpakkyApplication) -> None:
    """Initialize the spakky-event plugin.

    Registers event mediators, publishers, buses, and post-processors.
    """
    app.add(AsyncTransactionalEventPublishingAspect)
    app.add(TransactionalEventPublishingAspect)

    app.add(EventMediator)
    app.add(AsyncEventMediator)
    app.add(EventPublisher)
    app.add(AsyncEventPublisher)
    app.add(DirectEventBus)
    app.add(AsyncDirectEventBus)

    app.add(EventHandlerRegistrationPostProcessor)
