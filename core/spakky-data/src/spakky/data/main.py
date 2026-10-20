from spakky.core.application.application import SpakkyApplication

from spakky.data.aspects.transactional import (
    AsyncTransactionalAspect,
    TransactionalAspect,
)
from spakky.data.config import DataConfig
from spakky.data.persistency.aggregate_collector import AggregateCollector


def initialize(app: SpakkyApplication) -> None:
    """Initialize the spakky-data plugin.

    Registers the common configuration, sync aspect, and aggregate collector.
    The async aspect follows DataConfig, also consumed by persistence providers.
    """
    config = DataConfig()
    app.add(DataConfig)
    app.add(TransactionalAspect)
    app.add(AggregateCollector)

    if config.support_async_mode:
        app.add(AsyncTransactionalAspect)
