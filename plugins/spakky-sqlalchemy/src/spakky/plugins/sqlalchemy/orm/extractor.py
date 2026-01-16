"""Metadata extractor for domain entities.

This module provides a class-based metadata extractor for domain entity classes
to support SQLAlchemy imperative mapping.
"""

from dataclasses import MISSING, dataclass
from dataclasses import fields as dataclass_fields
from typing import Any, get_type_hints

from spakky.core.common.interfaces.equatable import IEquatable
from spakky.core.common.metadata import get_metadata
from spakky.core.common.types import is_optional, remove_none
from spakky.domain.models.entity import AbstractEntity

from spakky.plugins.sqlalchemy.orm.annotation import Table
from spakky.plugins.sqlalchemy.orm.metadata import Field


@dataclass(frozen=True)
class FieldMetadata:
    """Metadata for a single entity field.

    Attributes:
        name: The field name.
        python_type: The unwrapped Python type (without Optional).
        nullable: Whether the field allows None values.
        is_primary_key: Whether this field is the primary key.
        default: The default value, if any.
        default_factory: The default factory function, if any.
        field_info: Optional Field metadata from Annotated type hints.
    """

    name: str
    """The field name."""

    python_type: type
    """The unwrapped Python type (Optional removed)."""

    nullable: bool = False
    """Whether the field allows None values."""

    is_primary_key: bool = False
    """Whether this field is the primary key."""

    default: Any = None
    """The default value, if specified."""

    default_factory: Any = None
    """The default factory function, if specified."""

    field_info: Field | None = None
    """Optional Field metadata from Annotated type hints."""


@dataclass(frozen=True)
class EntityMetadata:
    """Metadata for an entity class.

    Attributes:
        entity_class: The original entity class.
        table_name: The database table name.
        fields: List of field metadata.
    """

    entity_class: type
    """The original entity class."""

    table_name: str
    """The database table name."""

    fields: tuple[FieldMetadata, ...]
    """Tuple of field metadata."""

    def get_field(self, name: str) -> FieldMetadata | None:
        """Get field metadata by name.

        Args:
            name: The field name.

        Returns:
            FieldMetadata if found, None otherwise.
        """
        for field in self.fields:
            if field.name == name:
                return field
        return None

    @property
    def primary_key_field(self) -> FieldMetadata | None:
        """Get the primary key field.

        Returns:
            FieldMetadata for primary key, or None if not found.
        """
        for field in self.fields:
            if field.is_primary_key:
                return field
        return None


# Fields that are always present in AbstractEntity
ENTITY_COMMON_FIELDS: frozenset[str] = frozenset(
    {
        "uid",
        "version",
        "created_at",
        "updated_at",
    }
)

# Fields to skip during extraction (internal implementation details)
SKIP_FIELDS: frozenset[str] = frozenset(
    {
        "_AbstractEntity__initialized",
        "_AbstractAggregateRoot__events",
    }
)


class MetadataExtractor:
    """Extracts ORM metadata from domain entity classes.

    This class analyzes domain entity classes decorated with @Table annotation
    and extracts all information needed for SQLAlchemy imperative mapping.
    """

    def extract(self, entity_cls: type[AbstractEntity[IEquatable]]) -> EntityMetadata:
        """Extract ORM metadata from a domain entity class.

        Args:
            entity_cls: The entity class to analyze. Must be a subclass of AbstractEntity
                and decorated with @Table annotation.

        Returns:
            EntityMetadata containing table name and field information.

        Raises:
            ValueError: If entity_cls does not have @Table annotation.

        Examples:
            >>> from uuid import UUID
            >>> from spakky.domain.models.entity import AbstractEntity
            >>> from spakky.core.common.mutability import mutable
            >>>
            >>> @mutable
            ... @Table(name="users")
            ... class User(AbstractEntity[UUID]):
            ...     name: str
            ...     email: str | None
            ...
            ...     @classmethod
            ...     def next_id(cls) -> UUID: ...
            ...     def validate(self) -> None: ...
            >>>
            >>> extractor = MetadataExtractor()
            >>> metadata = extractor.extract(User)
            >>> metadata.table_name
            'users'
            >>> len(metadata.fields)
            6
        """
        # Get table name from @Table annotation
        table_annotation = Table.get(entity_cls)

        # Get type hints for accurate type information
        try:
            hints = get_type_hints(entity_cls, include_extras=True)
        except Exception:  # pragma: no cover
            hints = {}

        # Extract field metadata
        extracted_fields: list[FieldMetadata] = []

        for dc_field in dataclass_fields(entity_cls):
            field_name = dc_field.name

            # Skip private/internal fields
            if field_name.startswith("_"):
                continue

            # Skip explicitly excluded fields
            if field_name in SKIP_FIELDS:
                continue

            # Get type hint
            hint = hints.get(field_name, dc_field.type)

            # Check if nullable and unwrap Optional
            nullable = is_optional(hint)
            python_type = remove_none(hint) if nullable else hint

            # Extract Field metadata from Annotated if present
            field_info: Field | None = None
            try:
                _, metadata_list = get_metadata(hint)
                for meta in metadata_list:
                    if isinstance(meta, Field):
                        field_info = meta
                        break
            except Exception:  # pragma: no cover
                pass

            # Determine if this is the primary key
            is_primary_key = field_name == "uid"

            # Get default value
            default: Any = None
            default_factory: Any = None

            if dc_field.default is not MISSING:
                default = dc_field.default
            if dc_field.default_factory is not MISSING:
                default_factory = dc_field.default_factory

            extracted_fields.append(
                FieldMetadata(
                    name=field_name,
                    python_type=python_type,
                    nullable=nullable,
                    is_primary_key=is_primary_key,
                    default=default,
                    default_factory=default_factory,
                    field_info=field_info,
                )
            )

        return EntityMetadata(
            entity_class=entity_cls,
            table_name=table_annotation.name,
            fields=tuple(extracted_fields),
        )
