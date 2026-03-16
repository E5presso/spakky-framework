from spakky.core.application.application import SpakkyApplication

from spakky.data.aspects.transactional import (
    AsyncTransactionalAspect,
    TransactionalAspect,
)
from spakky.data.persistency.aggregate_collector import AggregateCollector


def initialize(app: SpakkyApplication) -> None:
    """Initialize the spakky-data plugin.

    Registers transactional aspects and the aggregate collector.
    """
    app.add(AsyncTransactionalAspect)
    app.add(TransactionalAspect)
    app.add(AggregateCollector)
