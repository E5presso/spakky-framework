"""OneToOne relationship metadata for SQLAlchemy ORM."""

from typing import Generic

from spakky.core.common.mutability import mutable
from spakky.core.common.types import ClassT

from spakky.plugins.sqlalchemy.orm.relationships.base import (
    AbstractRelationship,
    RelationType,
)


@mutable
class OneToOne(AbstractRelationship[ClassT], Generic[ClassT]):
    """One-to-one relationship metadata.

    Use in Annotated type hints to define a one-to-one relationship
    where one entity has exactly one related entity.

    The field type should be the target entity type, optionally with None
    for nullable relationships.

    In SQLAlchemy, this is implemented as a relationship with uselist=False.

    Examples:
        >>> from typing import Annotated
        >>> from dataclasses import dataclass
        >>> from spakky.plugins.sqlalchemy.orm.relationships import OneToOne
        >>> from spakky.plugins.sqlalchemy.orm.table import Table
        >>>
        >>> @Table()
        >>> @dataclass
        >>> class User:
        ...     # User has exactly one Profile
        ...     profile: Annotated[Profile, OneToOne(back_populates="user")]
        >>>
        >>> @Table()
        >>> @dataclass
        >>> class Profile:
        ...     # Profile belongs to exactly one User
        ...     user: Annotated[User, OneToOne(back_populates="profile")]
        >>>
        >>> @Table()
        >>> @dataclass
        >>> class Employee:
        ...     # Optional one-to-one: Employee may have a ParkingSpot
        ...     parking_spot: Annotated[ParkingSpot | None, OneToOne(back_populates="employee")]
    """

    @property
    def relation_type(self) -> RelationType:
        """Get the relationship type.

        Returns:
            RelationType.ONE_TO_ONE
        """
        return RelationType.ONE_TO_ONE
