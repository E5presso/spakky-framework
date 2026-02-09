"""Foreign key constraint metadata for SQLAlchemy ORM."""

from enum import StrEnum
from typing import Generic

from spakky.core.common.mutability import mutable
from spakky.core.common.types import ClassT

from spakky.plugins.sqlalchemy.orm.constraints.base import AbstractConstraint
from spakky.plugins.sqlalchemy.orm.entity_ref import EntityRef


class ReferentialAction(StrEnum):
    """Referential actions for foreign key constraints.

    Defines what happens when the referenced row is updated or deleted.
    Maps directly to SQL standard referential actions.
    """

    CASCADE = "CASCADE"
    """Automatically update/delete the dependent rows."""

    SET_NULL = "SET NULL"
    """Set the foreign key column to NULL."""

    SET_DEFAULT = "SET DEFAULT"
    """Set the foreign key column to its default value."""

    RESTRICT = "RESTRICT"
    """Prevent the update/delete if dependent rows exist."""

    NO_ACTION = "NO ACTION"
    """Similar to RESTRICT but deferred until end of transaction."""


@mutable
class ForeignKey(AbstractConstraint, Generic[ClassT]):
    """Foreign key constraint metadata.

    Use in Annotated type hints to define a relationship to another table.
    Maps directly to SQLAlchemy's ForeignKey constraint.

    Examples:
        >>> from typing import Annotated
        >>> from spakky.plugins.sqlalchemy.orm.constraints import (
        ...     ColumnRef, ForeignKey, ReferentialAction
        ... )
        >>>
        >>> class User:
        ...     id: Annotated[int, PrimaryKey()]
        >>>
        >>> class Post:
        ...     # Type-safe foreign key with lambda accessor (recommended)
        ...     user_id: Annotated[int, ForeignKey(
        ...         ColumnRef(User, lambda t: t.id)
        ...     )]
        ...
        ...     # Type-safe with string field name
        ...     author_id: Annotated[int, ForeignKey(
        ...         ColumnRef(User, "id"),
        ...         on_delete=ReferentialAction.CASCADE
        ...     )]
        ...
        ...     # String-based (backward compatible)
        ...     category_id: Annotated[int, ForeignKey(
        ...         "category.id",
        ...         on_delete=ReferentialAction.SET_NULL
        ...     )]
    """

    column: EntityRef[ClassT] | str
    """Referenced column.

    Can be specified as:
    - `ColumnRef(Entity, lambda t: t.column)`: Type-safe with lambda accessor
    - `ColumnRef(Entity, "column")`: Type-safe with string
    - `str`: String format 'table.column' (backward compatible)
    """

    on_delete: ReferentialAction | None = None
    """Action to take when referenced row is deleted."""

    on_update: ReferentialAction | None = None
    """Action to take when referenced row is updated."""

    name: str | None = None
    """Custom name for the foreign key constraint."""
