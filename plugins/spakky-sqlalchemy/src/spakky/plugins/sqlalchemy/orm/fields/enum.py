"""Enum field metadata for SQLAlchemy ORM."""

from enum import Enum
from typing import TypeVar

from spakky.core.common.mutability import mutable

from spakky.plugins.sqlalchemy.orm.fields.base import AbstractField

EnumT = TypeVar("EnumT", bound=Enum)


@mutable
class EnumField(AbstractField[EnumT]):
    """Metadata annotation for enum fields.

    Maps to SQLAlchemy's Enum type. Stores enumerated values.

    Examples:
        >>> from typing import Annotated
        >>> from enum import Enum
        >>> from spakky.plugins.sqlalchemy.orm.fields.enum import EnumField
        >>>
        >>> class UserRole(Enum):
        ...     ADMIN = "admin"
        ...     USER = "user"
        ...     GUEST = "guest"
        >>>
        >>> class User:
        ...     role: Annotated[UserRole, EnumField(enum_class=UserRole)]
    """

    enum_class: type[EnumT]
    """The Python Enum class to use."""

    native_enum: bool = True
    """Use database's native ENUM type if available."""
