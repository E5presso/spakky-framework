from spakky.core.application.application import SpakkyApplication

from spakky.event.aspects.transactional_event_publishing import (
    AsyncTransactionalEventPublishingAspect,
    TransactionalEventPublishingAspect,
)
from spakky.event.mediator.domain_event_mediator import (
    AsyncDomainEventMediator,
    DomainEventMediator,
)
from spakky.event.post_processor import EventHandlerRegistrationPostProcessor
from spakky.event.publisher.domain_event_publisher import (
    AsyncDomainEventPublisher,
    DomainEventPublisher,
)


def initialize(app: SpakkyApplication) -> None:
    # Register aspects for transactional event publishing
    app.add(AsyncTransactionalEventPublishingAspect)
    app.add(TransactionalEventPublishingAspect)

    # Register in-process event infrastructure
    app.add(DomainEventMediator)
    app.add(AsyncDomainEventMediator)
    app.add(DomainEventPublisher)
    app.add(AsyncDomainEventPublisher)

    # Register post-processor for auto-registering @EventHandler methods
    app.add(EventHandlerRegistrationPostProcessor)
