"""Model registry for SQLAlchemy ORM."""

from logging import getLogger
from typing import Any

from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.sqlalchemy.orm.constraints.index import Index
from spakky.plugins.sqlalchemy.orm.constraints.unique import Unique
from spakky.plugins.sqlalchemy.orm.extractor import ColumnInfo, Extractor, ModelInfo
from spakky.plugins.sqlalchemy.orm.type_mapper import TypeMapper
from sqlalchemy import Index as SAIndex
from sqlalchemy import MetaData, UniqueConstraint
from sqlalchemy import Table as SATable
from sqlalchemy.orm import registry

logger = getLogger(__name__)


@Pod()
class ModelRegistry:
    """Registry for SQLAlchemy ORM models.

    This is a singleton Pod that manages SQLAlchemy's registry and
    automatically maps dataclass entities to ORM models during
    application startup.

    The registry is populated by TableRegistrationPostProcessor which
    discovers all @Table annotated classes and registers them here.

    Example:
        >>> from spakky.plugins.sqlalchemy.orm.registry import ModelRegistry
        >>>
        >>> # Get the registry from container
        >>> model_registry = container.get(ModelRegistry)
        >>>
        >>> # Register a table manually (usually done automatically)
        >>> model_registry.register(UserEntity)
        >>>
        >>> # Access the underlying SQLAlchemy metadata
        >>> metadata = model_registry.metadata
    """

    __registry: registry
    """SQLAlchemy registry for imperative mapping."""

    __extractor: Extractor
    """Extractor for extracting model info from entity classes."""

    __type_mapper: TypeMapper
    """Type mapper for converting field metadata to SQLAlchemy types."""

    __registered_entities: dict[type, SATable]
    """Map of registered entity classes to their SQLAlchemy Table objects."""

    def __init__(self, extractor: Extractor, type_mapper: TypeMapper) -> None:
        """Initialize the model registry.

        Args:
            extractor: Extractor for extracting model metadata.
            type_mapper: Type mapper for SQLAlchemy column types.
        """
        self.__registry = registry()
        self.__extractor = extractor
        self.__type_mapper = type_mapper
        self.__registered_entities = {}

    @property
    def metadata(self) -> MetaData:
        """Get the SQLAlchemy MetaData object.

        Returns:
            The MetaData containing all registered tables.
        """
        return self.__registry.metadata

    @property
    def sqlalchemy_registry(self) -> registry:
        """Get the underlying SQLAlchemy registry.

        Returns:
            The SQLAlchemy registry instance.
        """
        return self.__registry

    @property
    def registered_entities(self) -> dict[type, SATable]:
        """Get all registered entity classes and their tables.

        Returns:
            Dictionary mapping entity classes to SQLAlchemy Table objects.
        """
        return self.__registered_entities.copy()

    def is_registered(self, entity_cls: type) -> bool:
        """Check if an entity class is already registered.

        Args:
            entity_cls: The entity class to check.

        Returns:
            True if the entity is registered.
        """
        return entity_cls in self.__registered_entities

    def register(self, entity_cls: type) -> SATable:
        """Register a dataclass entity as a SQLAlchemy ORM model.

        Uses the Extractor to extract model metadata and creates a
        SQLAlchemy Table with the appropriate columns and constraints.

        Args:
            entity_cls: The dataclass entity class to register.

        Returns:
            The created SQLAlchemy Table object.

        Raises:
            TableDefinitionNotFoundError: If entity has no @Table annotation.
        """
        if entity_cls in self.__registered_entities:
            logger.debug(
                f"[{type(self).__name__}] Entity {entity_cls.__name__!r} already registered"
            )
            return self.__registered_entities[entity_cls]

        model_info: ModelInfo = self.__extractor.extract(entity_cls)
        columns: list[Any] = self._build_columns(model_info)
        table_constraints: list[Any] = self._build_table_constraints(model_info)

        sa_table = SATable(
            model_info.table_name,
            self.__registry.metadata,
            *columns,
            *table_constraints,
        )

        self.__registry.map_imperatively(entity_cls, sa_table)
        self.__registered_entities[entity_cls] = sa_table

        logger.debug(
            f"[{type(self).__name__}] Registered entity {entity_cls.__name__!r} "
            f"as table {model_info.table_name!r}"
        )

        return sa_table

    def _build_columns(self, model_info: ModelInfo) -> list[Any]:
        """Build SQLAlchemy Column objects from model info.

        Args:
            model_info: Extracted model information.

        Returns:
            List of SQLAlchemy Column objects.
        """
        columns: list[Any] = []
        for col_name, col_info in model_info.columns.items():
            column = self.__type_mapper.create_column(col_name, col_info)
            columns.append(column)
        return columns

    def _build_table_constraints(
        self, model_info: ModelInfo
    ) -> list[UniqueConstraint | SAIndex]:
        """Build table-level constraints from model info.

        Named Unique constraints and named/unique Index constraints
        are handled at the table level rather than column level.

        Args:
            model_info: Extracted model information.

        Returns:
            List of SQLAlchemy table-level constraint objects.
        """
        constraints: list[UniqueConstraint | SAIndex] = []

        for col_name, col_info in model_info.columns.items():
            column_name = col_info.field_metadata.name or col_name
            constraints.extend(
                self._collect_column_table_constraints(column_name, col_info)
            )

        return constraints

    def _collect_column_table_constraints(
        self, column_name: str, col_info: ColumnInfo
    ) -> list[UniqueConstraint | SAIndex]:
        """Collect table-level constraints for a single column.

        Args:
            column_name: The database column name.
            col_info: Column information.

        Returns:
            List of table-level constraints for this column.
        """
        constraints: list[UniqueConstraint | SAIndex] = []

        for constraint in col_info.constraints:
            # Named Unique → Table-level UniqueConstraint
            if isinstance(constraint, Unique) and constraint.name is not None:
                constraints.append(UniqueConstraint(column_name, name=constraint.name))

            # Named Index or unique Index → Table-level Index
            if isinstance(constraint, Index) and (
                constraint.name is not None or constraint.unique
            ):
                constraints.append(
                    SAIndex(constraint.name, column_name, unique=constraint.unique)
                )

        return constraints

    def get_table(self, entity_cls: type) -> SATable | None:
        """Get the SQLAlchemy Table for a registered entity.

        Args:
            entity_cls: The entity class to look up.

        Returns:
            The SQLAlchemy Table, or None if not registered.
        """
        return self.__registered_entities.get(entity_cls)
