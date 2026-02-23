from spakky.core.application.application import SpakkyApplication

from spakky.plugins.sqlalchemy.common.config import SQLAlchemyConnectionConfig
from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
)
from spakky.plugins.sqlalchemy.persistency.transaction import (
    AsyncTransaction,
    Transaction,
)


def initialize(app: SpakkyApplication) -> None:
    """Initialize the SQLAlchemy plugin.

    Registers SQLAlchemy configuration, schema registry, session managers,
    and transaction handlers. Async Pods (AsyncSessionManager, AsyncTransaction)
    are only registered when support_async_mode is True in the configuration.

    Args:
        app: The Spakky application instance.
    """
    config = SQLAlchemyConnectionConfig()

    app.add(SQLAlchemyConnectionConfig)
    app.add(SchemaRegistry)

    app.add(SessionManager)
    app.add(Transaction)

    if config.support_async_mode:
        app.add(AsyncSessionManager)
        app.add(AsyncTransaction)
