from spakky.core.application.application import SpakkyApplication

from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry


def initialize(app: SpakkyApplication) -> None:
    app.add(SchemaRegistry)
