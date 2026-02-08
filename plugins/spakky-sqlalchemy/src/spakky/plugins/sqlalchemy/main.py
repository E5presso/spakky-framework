"""Plugin initialization for spakky-sqlalchemy.

Registers ORM components and post-processors that enable automatic
table registration with SQLAlchemy from @Table annotated dataclasses.
"""

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.sqlalchemy.orm.extractor import Extractor
from spakky.plugins.sqlalchemy.orm.registry import ModelRegistry
from spakky.plugins.sqlalchemy.orm.type_mapper import TypeMapper
from spakky.plugins.sqlalchemy.post_processors import TableRegistrationPostProcessor


def initialize(app: SpakkyApplication) -> None:
    """Initialize the SQLAlchemy plugin.

    Registers ORM components for automatic table registration:
    - Extractor: Extracts model metadata from @Table annotated classes
    - TypeMapper: Maps field annotations to SQLAlchemy column types
    - ModelRegistry: Manages SQLAlchemy registry and model registration
    - TableRegistrationPostProcessor: Auto-discovers and registers tables

    Args:
        app: The Spakky application instance.
    """
    # Core ORM components
    app.add(Extractor)
    app.add(TypeMapper)
    app.add(ModelRegistry)

    # Post-processor for automatic table registration
    app.add(TableRegistrationPostProcessor)
