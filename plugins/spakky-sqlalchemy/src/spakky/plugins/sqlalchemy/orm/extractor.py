"""Extractor for SQLAlchemy ORM metadata."""

import datetime
import decimal
import enum
import uuid
from collections.abc import Collection, Set
from dataclasses import MISSING, Field, dataclass, fields
from typing import (
    Annotated,
    Any,
    Callable,
    ClassVar,
    get_args,
    get_origin,
    get_type_hints,
)

from spakky.core.common.types import is_optional, remove_none
from spakky.core.pod.annotations.pod import Pod
from spakky.core.utils.naming import is_public_name

from spakky.plugins.sqlalchemy.orm.constraints.base import AbstractConstraint
from spakky.plugins.sqlalchemy.orm.error import AbstractSpakkyORMError
from spakky.plugins.sqlalchemy.orm.fields.base import AbstractField
from spakky.plugins.sqlalchemy.orm.fields.binary import Binary
from spakky.plugins.sqlalchemy.orm.fields.boolean import Boolean
from spakky.plugins.sqlalchemy.orm.fields.datetime import Date, DateTime, Time
from spakky.plugins.sqlalchemy.orm.fields.enum import EnumField
from spakky.plugins.sqlalchemy.orm.fields.json import JSON
from spakky.plugins.sqlalchemy.orm.fields.numeric import Float, Integer, Numeric
from spakky.plugins.sqlalchemy.orm.fields.string import String
from spakky.plugins.sqlalchemy.orm.fields.uuid import Uuid
from spakky.plugins.sqlalchemy.orm.relationships.base import (
    AbstractRelationship,
    RelationType,
)
from spakky.plugins.sqlalchemy.orm.table import Table

COLLECTION_TYPES: dict[type, type] = {
    list: list,
    set: set,
    frozenset: frozenset,
    Collection: list,
    Set: set,
}
"""Mapping of collection type origins to their concrete collection class."""


@dataclass
class ColumnInfo:
    """Extracted column information."""

    name: str
    field_metadata: AbstractField[Any]
    constraints: list[AbstractConstraint]
    python_type: Any
    default: Any = None
    default_factory: Callable[[], Any] | None = None
    nullable: bool = False


@dataclass
class RelationInfo:
    """Extracted relationship information."""

    name: str
    """Field name in the dataclass."""

    relationship_metadata: AbstractRelationship
    """The relationship annotation (OneToMany, ManyToOne)."""

    target_entity: type
    """The target entity class of the relationship."""

    collection_class: type | None
    """For OneToMany: the collection type (list, set, etc.). None for ManyToOne."""

    nullable: bool
    """Whether the relationship is optional (ManyToOne only)."""


@dataclass
class ModelInfo:
    """Extracted model information."""

    table_name: str
    columns: dict[str, ColumnInfo]
    relations: list[RelationInfo]


class TableDefinitionNotFoundError(AbstractSpakkyORMError):
    """Raised when no Table definition is found on an entity class."""

    message: ClassVar[str] = "No Table definition found on entity class."


class MissingRelationshipAnnotationError(AbstractSpakkyORMError):
    """Raised when a collection of @Table entities lacks relationship annotation.

    This error occurs when a field type like `list[Entity]` is found where
    `Entity` has a @Table annotation, but the field lacks a relationship
    annotation (OneToMany/ManyToOne). This likely indicates a missing
    relationship annotation rather than intentional JSON storage.

    Args (via args tuple):
        field_name: The field name that has the issue.
        element_type: The @Table-annotated element type.
    """

    message = "Collection of @Table entity lacks relationship annotation"


@Pod()
class Extractor:
    """Extracts SQLAlchemy model information from entity classes."""

    def extract(self, entity_cls: type) -> ModelInfo:
        """Extract metadata from an entity class.

        Args:
            entity_cls: The entity class to extract metadata from.

        Returns:
            ModelInfo: The extracted model information.
        """
        table_annotation = Table.get_or_none(entity_cls)
        if table_annotation is None:
            raise TableDefinitionNotFoundError()

        columns: dict[str, ColumnInfo] = {}
        relations: list[RelationInfo] = []
        type_hints: dict[str, Any] = get_type_hints(entity_cls, include_extras=True)
        dataclass_fields: dict[str, Field[Any]] = {
            f.name: f for f in fields(entity_cls)
        }

        for name, field_type in (
            (n, t)
            for n, t in type_hints.items()
            if n in dataclass_fields and is_public_name(n)
        ):
            dataclass_field: Field[Any] = dataclass_fields[name]

            actual_type: type[Any | None] = field_type
            field_metadata: AbstractField[Any] | None = None
            relationship_metadata: AbstractRelationship | None = None
            constraints: list[AbstractConstraint] = []

            if get_origin(field_type) is Annotated:
                actual_type = AbstractField.get_actual_type(field_type)
                field_metadata = AbstractField.get_or_none(field_type)
                relationship_metadata = AbstractRelationship.get_or_none(field_type)
                constraints = AbstractConstraint.all(field_type)

            # Handle relationship fields separately
            if relationship_metadata is not None:
                relation_info = self._extract_relation(
                    name, actual_type, relationship_metadata
                )
                if relation_info is not None:
                    relations.append(relation_info)
                continue

            # Validate: collection of @Table entities without relationship annotation
            # Skip validation if explicit field metadata is provided (intentional mapping)
            if field_metadata is None:
                self._validate_not_unmapped_entity_collection(name, actual_type)

            nullable: bool = is_optional(actual_type)
            if nullable:
                actual_type = remove_none(actual_type)

            if field_metadata is None:
                field_metadata = self._infer_field_type(actual_type)

            columns[name] = ColumnInfo(
                name=name,
                field_metadata=field_metadata,
                constraints=constraints,
                python_type=actual_type,
                default=(
                    dataclass_field.default
                    if dataclass_field.default is not MISSING
                    else None
                ),
                default_factory=(
                    dataclass_field.default_factory
                    if dataclass_field.default_factory is not MISSING
                    else None
                ),
                nullable=nullable,
            )

        return ModelInfo(
            table_name=table_annotation.table_name,
            columns=columns,
            relations=relations,
        )

    def _extract_relation(
        self,
        name: str,
        field_type: type,
        relationship_metadata: AbstractRelationship,
    ) -> RelationInfo | None:
        """Extract relationship information from a field.

        Args:
            name: The field name.
            field_type: The field type (actual type from Annotated).
            relationship_metadata: The relationship annotation.

        Returns:
            RelationInfo if valid relationship, None otherwise.
        """
        origin = get_origin(field_type)

        # OneToMany: Collection[Entity] pattern
        if relationship_metadata.relation_type == RelationType.ONE_TO_MANY:
            collection_class: type | None = None
            if origin is not None and isinstance(origin, type):
                collection_class = COLLECTION_TYPES.get(origin)
            if collection_class is not None:
                args = get_args(field_type)
                if args:
                    target_entity = args[0]
                    return RelationInfo(
                        name=name,
                        relationship_metadata=relationship_metadata,
                        target_entity=target_entity,
                        collection_class=collection_class,
                        nullable=False,
                    )
            return None  # pragma: no cover

        # ManyToOne: Entity or Entity | None pattern
        if relationship_metadata.relation_type == RelationType.MANY_TO_ONE:
            nullable = is_optional(field_type)
            target_entity = remove_none(field_type) if nullable else field_type
            return RelationInfo(
                name=name,
                relationship_metadata=relationship_metadata,
                target_entity=target_entity,
                collection_class=None,
                nullable=nullable,
            )

        # OneToOne: Entity or Entity | None pattern (same as ManyToOne but uselist=False)
        if relationship_metadata.relation_type == RelationType.ONE_TO_ONE:
            nullable = is_optional(field_type)
            target_entity = remove_none(field_type) if nullable else field_type
            return RelationInfo(
                name=name,
                relationship_metadata=relationship_metadata,
                target_entity=target_entity,
                collection_class=None,
                nullable=nullable,
            )

        return None  # pragma: no cover

    def _validate_not_unmapped_entity_collection(
        self, field_name: str, field_type: type
    ) -> None:
        """Validate that a field is not an unmapped collection of @Table entities.

        Raises MissingRelationshipAnnotationError if the field is a collection
        (list, set, frozenset) of @Table-annotated entities without a
        relationship annotation.

        Args:
            field_name: The field name to validate.
            field_type: The field type to check.

        Raises:
            MissingRelationshipAnnotationError: If validation fails.
        """
        origin = get_origin(field_type)
        if origin is None or not isinstance(origin, type):
            return

        # Check if it's a collection type
        if origin not in COLLECTION_TYPES:
            return

        # Get the element type
        args = get_args(field_type)
        if not args:
            return  # pragma: no cover

        element_type = args[0]

        # Check if element type has @Table annotation
        if not isinstance(element_type, type):
            return  # pragma: no cover

        if Table.get_or_none(element_type) is not None:
            raise MissingRelationshipAnnotationError(field_name, element_type)

    def _infer_field_type(self, type_hint: type[Any]) -> AbstractField[Any]:
        """Infer AbstractField from Python type."""
        if type_hint is int:
            return Integer()
        if type_hint is float:
            return Float()
        if type_hint is str:
            return String()
        if type_hint is bool:
            return Boolean()
        if type_hint is datetime.datetime:
            return DateTime()
        if type_hint is datetime.date:
            return Date()
        if type_hint is datetime.time:
            return Time()
        if type_hint is uuid.UUID:
            return Uuid()
        if type_hint is decimal.Decimal:
            return Numeric()
        if type_hint is bytes:
            return Binary()

        origin: Any | None = get_origin(type_hint)
        if origin in (dict, list) or type_hint in (dict, list):
            return JSON()

        if issubclass(type_hint, enum.Enum):
            return EnumField(enum_class=type_hint)

        # Fallback
        return String()
