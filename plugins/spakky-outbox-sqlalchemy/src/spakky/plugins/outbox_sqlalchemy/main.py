"""Plugin initialization entry point."""

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.outbox_sqlalchemy.adapters.storage import (
    AsyncSqlAlchemyOutboxStorage,
    SqlAlchemyOutboxStorage,
)


def initialize(app: SpakkyApplication) -> None:
    """Initialize the Outbox SQLAlchemy plugin.

    Args:
        app: The Spakky application instance.
    """
    app.add(SqlAlchemyOutboxStorage)
    app.add(AsyncSqlAlchemyOutboxStorage)
