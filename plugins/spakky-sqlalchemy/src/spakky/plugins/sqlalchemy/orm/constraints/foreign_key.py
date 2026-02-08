"""Foreign key constraint metadata for SQLAlchemy ORM."""

from enum import StrEnum

from spakky.core.common.mutability import mutable

from spakky.plugins.sqlalchemy.orm.constraints.base import AbstractConstraint


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
class ForeignKey(AbstractConstraint):
    """Foreign key constraint metadata.

    Use in Annotated type hints to define a relationship to another table.
    Maps directly to SQLAlchemy's ForeignKey constraint.

    Examples:
        >>> from typing import Annotated
        >>> from spakky.plugins.sqlalchemy.orm.constraints.foreign_key import (
        ...     ForeignKey, ReferentialAction
        ... )
        >>>
        >>> class Post:
        ...     # Basic foreign key
        ...     user_id: Annotated[int, ForeignKey("user.id")]
        ...
        ...     # Foreign key with cascade delete
        ...     author_id: Annotated[int, ForeignKey(
        ...         "user.id",
        ...         on_delete=ReferentialAction.CASCADE
        ...     )]
        ...
        ...     # Foreign key with SET NULL on delete
        ...     category_id: Annotated[int, ForeignKey(
        ...         "category.id",
        ...         on_delete=ReferentialAction.SET_NULL
        ...     )]
    """

    column: str
    """Referenced column in format 'table.column'."""

    on_delete: ReferentialAction | None = None
    """Action to take when referenced row is deleted."""

    on_update: ReferentialAction | None = None
    """Action to take when referenced row is updated."""

    name: str | None = None
    """Custom name for the foreign key constraint."""
