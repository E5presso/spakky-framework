"""SQLAlchemy contribution for the spakky-event feature."""

from spakky.core.application.application import SpakkyApplication
from spakky.data.config import DataConfig

from spakky.plugins.sqlalchemy.event.store import (
    AsyncSqlAlchemyProcessedEventStore,
    SqlAlchemyProcessedEventStore,
)
from spakky.plugins.sqlalchemy.event.table import ProcessedEventTable


def initialize(app: SpakkyApplication) -> None:
    """Register the SQLAlchemy-backed processed-event store (inbox)."""
    config = DataConfig()

    app.add(ProcessedEventTable)
    app.add(SqlAlchemyProcessedEventStore)

    if config.support_async_mode:
        app.add(AsyncSqlAlchemyProcessedEventStore)
