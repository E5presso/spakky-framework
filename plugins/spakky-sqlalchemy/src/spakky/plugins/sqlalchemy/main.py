from spakky.core.application.application import SpakkyApplication

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
    app.add(SchemaRegistry)

    app.add(SessionManager)
    app.add(AsyncSessionManager)

    app.add(Transaction)
    app.add(AsyncTransaction)
