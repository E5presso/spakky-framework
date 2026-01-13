from spakky.core.application.application import SpakkyApplication

from spakky.data.aspects.transactional import (
    AsyncTransactionalAspect,
    TransactionalAspect,
)
from spakky.data.persistency.aggregate_collector import AggregateCollector


def initialize(app: SpakkyApplication) -> None:
    app.add(AsyncTransactionalAspect)
    app.add(TransactionalAspect)
    app.add(AggregateCollector)
