"""Unique constraint metadata for SQLAlchemy ORM."""

from spakky.core.common.mutability import mutable

from spakky.plugins.sqlalchemy.orm.constraints.base import AbstractConstraint


@mutable
class Unique(AbstractConstraint):
    """Unique constraint metadata.

    Use in Annotated type hints to enforce unique values for a field.

    Examples:
        >>> from typing import Annotated
        >>> from spakky.plugins.sqlalchemy.orm.fields.string import String
        >>> from spakky.plugins.sqlalchemy.orm.constraints.unique import Unique
        >>>
        >>> class User:
        ...     # Unique email
        ...     email: Annotated[str, String(length=255), Unique()]
        ...
        ...     # Unique with custom constraint name
        ...     username: Annotated[str, String(length=100), Unique(name="uq_user_username")]
    """

    name: str | None = None
    """Custom name for the unique constraint."""
