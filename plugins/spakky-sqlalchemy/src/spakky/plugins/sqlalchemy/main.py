from spakky.core.application.application import SpakkyApplication

from spakky.plugins.sqlalchemy.common.config import SQLAlchemyConnectionConfig
from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry
from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
    ConnectionManager,
)
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
)
from spakky.plugins.sqlalchemy.persistency.transaction import (
    AsyncTransaction,
    Transaction,
)

try:
    from spakky.plugins.sqlalchemy.outbox.storage import (
        AsyncSqlAlchemyOutboxStorage,
        SqlAlchemyOutboxStorage,
    )
    from spakky.plugins.sqlalchemy.outbox.table import OutboxMessageTable

    _HAS_OUTBOX = True
except ImportError:
    _HAS_OUTBOX = False


def initialize(app: SpakkyApplication) -> None:
    """Initialize the SQLAlchemy plugin.

    Registers SQLAlchemy configuration, schema registry, session managers,
    and transaction handlers. Async Pods (AsyncSessionManager, AsyncTransaction)
    are only registered when support_async_mode is True in the configuration.

    When spakky-outbox is installed, Outbox storage implementations are
    automatically registered (runtime detection).

    Args:
        app: The Spakky application instance.
    """
    config = SQLAlchemyConnectionConfig()

    app.add(SQLAlchemyConnectionConfig)
    app.add(SchemaRegistry)

    app.add(ConnectionManager)
    app.add(SessionManager)
    app.add(Transaction)

    if config.support_async_mode:
        app.add(AsyncConnectionManager)
        app.add(AsyncSessionManager)
        app.add(AsyncTransaction)

    if _HAS_OUTBOX:
        app.add(OutboxMessageTable)
        app.add(SqlAlchemyOutboxStorage)
        if config.support_async_mode:
            app.add(AsyncSqlAlchemyOutboxStorage)
