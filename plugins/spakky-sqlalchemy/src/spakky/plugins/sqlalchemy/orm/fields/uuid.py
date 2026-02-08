"""UUID field metadata for SQLAlchemy ORM."""

from uuid import UUID

from spakky.core.common.mutability import mutable

from spakky.plugins.sqlalchemy.orm.fields.base import AbstractField


@mutable
class Uuid(AbstractField[UUID]):
    """Metadata annotation for UUID fields.

    Maps to SQLAlchemy's Uuid type. Stores UUID values.

    Examples:
        >>> from typing import Annotated
        >>> from uuid import UUID
        >>> from spakky.plugins.sqlalchemy.orm.fields.uuid import Uuid
        >>>
        >>> class User:
        ...     id: Annotated[UUID, Uuid()]
        ...     external_id: Annotated[UUID, Uuid()]
    """

    as_uuid: bool = True
    """Return values as UUID objects (True) or strings (False)."""
