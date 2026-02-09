from spakky.core.common.mutability import mutable

from spakky.plugins.sqlalchemy.orm.fields.base import AbstractField


@mutable
class String(AbstractField[str]):
    """Metadata annotation for string fields in SQLAlchemy ORM.

    Maps to SQLAlchemy's String type.

    Examples:
        >>> from typing import Annotated
        >>> from spakky.plugins.sqlalchemy.orm.fields.string import String
        >>>
        >>> class User:
        ...     name: Annotated[str, String(length=100)]
        ...     email: Annotated[str, String(length=255, collation='utf8mb4_unicode_ci')]
    """

    length: int = 255
    """The maximum length of the string field."""

    collation: str | None = None
    """Collation for string comparison and sorting."""
