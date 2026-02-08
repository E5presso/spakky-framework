"""Index metadata for SQLAlchemy ORM."""

from spakky.core.common.mutability import mutable

from spakky.plugins.sqlalchemy.orm.constraints.base import AbstractConstraint


@mutable
class Index(AbstractConstraint):
    """Index metadata for database optimization.

    Use in Annotated type hints to create an index on a field.

    Examples:
        >>> from typing import Annotated
        >>> from spakky.plugins.sqlalchemy.orm.fields.string import String
        >>> from spakky.plugins.sqlalchemy.orm.constraints.index import Index
        >>>
        >>> class User:
        ...     # Regular index
        ...     email: Annotated[str, String(length=255), Index()]
        ...
        ...     # Unique index with custom name
        ...     username: Annotated[str, String(length=100), Index(unique=True, name="idx_user_username")]
    """

    name: str | None = None
    """Custom name for the index."""

    unique: bool = False
    """Whether this is a unique index."""
