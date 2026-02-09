"""ManyToOne relationship metadata for SQLAlchemy ORM."""

from typing import Generic
from spakky.core.common.mutability import mutable

from spakky.plugins.sqlalchemy.orm.relationships.base import (
    AbstractRelationship,
    RelationType,
)
from spakky.core.common.types import ClassT


@mutable
class ManyToOne(AbstractRelationship[ClassT], Generic[ClassT]):
    """Many-to-one relationship metadata.

    Use in Annotated type hints to define a many-to-one relationship
    where many entities reference a single entity.

    The field type should be the target entity type, optionally with None
    for nullable relationships.

    Examples:
        >>> from typing import Annotated
        >>> from dataclasses import dataclass
        >>> from spakky.plugins.sqlalchemy.orm.relationships import ManyToOne
        >>> from spakky.plugins.sqlalchemy.orm.table import Table
        >>>
        >>> @Table()
        >>> @dataclass
        >>> class OrderItem:
        ...     # Required reference: OrderItem belongs to Order
        ...     order: Annotated[Order, ManyToOne(back_populates="items")]
        >>>
        >>> @Table()
        >>> @dataclass
        >>> class Post:
        ...     # Optional reference: Post may have a Category
        ...     category: Annotated[Category | None, ManyToOne(back_populates="posts")]
        >>>
        >>> @Table()
        >>> @dataclass
        >>> class Comment:
        ...     # With custom loading strategy
        ...     author: Annotated[User, ManyToOne(back_populates="comments", lazy="joined")]
    """

    @property
    def relation_type(self) -> RelationType:
        """Get the relationship type.

        Returns:
            RelationType.MANY_TO_ONE
        """
        return RelationType.MANY_TO_ONE
