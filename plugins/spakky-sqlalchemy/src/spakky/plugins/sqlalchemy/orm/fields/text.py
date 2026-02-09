"""Text field metadata for SQLAlchemy ORM."""

from spakky.core.common.mutability import mutable

from spakky.plugins.sqlalchemy.orm.fields.base import AbstractField


@mutable
class Text(AbstractField[str]):
    """Metadata annotation for large text fields.

    Maps to SQLAlchemy's Text type for storing long text content
    without a specific length limit.

    Examples:
        >>> from typing import Annotated
        >>> from spakky.plugins.sqlalchemy.orm.fields.text import Text
        >>>
        >>> class Article:
        ...     content: Annotated[str, Text()]
        ...     description: Annotated[str, Text(collation="utf8mb4_unicode_ci")]
    """

    collation: str | None = None
    """Collation for text comparison and sorting."""
