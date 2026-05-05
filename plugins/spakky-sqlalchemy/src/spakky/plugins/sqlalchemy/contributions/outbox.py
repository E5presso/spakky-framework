"""SQLAlchemy contribution for the spakky-outbox feature."""

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.sqlalchemy.common.config import SQLAlchemyConnectionConfig
from spakky.plugins.sqlalchemy.outbox.storage import (
    AsyncSqlAlchemyOutboxStorage,
    SqlAlchemyOutboxStorage,
)
from spakky.plugins.sqlalchemy.outbox.table import OutboxMessageTable


def initialize(app: SpakkyApplication) -> None:
    """Register SQLAlchemy-backed Outbox infrastructure."""
    config = SQLAlchemyConnectionConfig()

    app.add(OutboxMessageTable)
    app.add(SqlAlchemyOutboxStorage)

    if config.support_async_mode:
        app.add(AsyncSqlAlchemyOutboxStorage)
