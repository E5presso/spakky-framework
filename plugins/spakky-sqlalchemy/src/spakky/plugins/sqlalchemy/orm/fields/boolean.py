"""Boolean field metadata for SQLAlchemy ORM."""

from spakky.core.common.mutability import mutable

from spakky.plugins.sqlalchemy.orm.fields.base import AbstractField


@mutable
class Boolean(AbstractField[bool]):
    """Metadata annotation for boolean fields.

    Maps to SQLAlchemy's Boolean type. Stores True/False values.

    Examples:
        >>> from typing import Annotated
        >>> from spakky.plugins.sqlalchemy.orm.fields.boolean import Boolean
        >>>
        >>> class User:
        ...     is_active: Annotated[bool, Boolean()]
        ...     is_admin: Annotated[bool, Boolean()]
    """
