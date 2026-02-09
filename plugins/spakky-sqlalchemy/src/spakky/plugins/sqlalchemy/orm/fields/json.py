"""JSON field metadata for SQLAlchemy ORM."""

from typing import Any

from spakky.core.common.mutability import mutable

from spakky.plugins.sqlalchemy.orm.fields.base import AbstractField


@mutable
class JSON(AbstractField[dict[str, Any]]):
    """Metadata annotation for JSON fields.

    Maps to SQLAlchemy's JSON type. Stores JSON-serializable data.

    Examples:
        >>> from typing import Annotated, Any
        >>> from spakky.plugins.sqlalchemy.orm.fields.json import JSON
        >>>
        >>> class User:
        ...     settings: Annotated[dict[str, Any], JSON()]
        ...     metadata: Annotated[dict[str, Any], JSON(none_as_null=True)]
    """

    none_as_null: bool = False
    """Persist Python None as SQL NULL rather than JSON 'null'."""
