from spakky.core.application.application import SpakkyApplication

from spakky.event.aspects.transactional_event_publishing import (
    AsyncTransactionalEventPublishingAspect,
    TransactionalEventPublishingAspect,
)


def initialize(app: SpakkyApplication) -> None:
    app.add(AsyncTransactionalEventPublishingAspect)
    app.add(TransactionalEventPublishingAspect)
