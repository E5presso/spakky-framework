"""OneToMany relationship metadata for SQLAlchemy ORM."""

from spakky.core.common.mutability import mutable

from spakky.plugins.sqlalchemy.orm.relationships.base import (
    AbstractRelationship,
    RelationType,
)


@mutable
class OneToMany(AbstractRelationship):
    """One-to-many relationship metadata.

    Use in Annotated type hints to define a one-to-many relationship
    where one entity has a collection of related entities.

    The field type should be a collection type (list, set, frozenset)
    containing the target entity type.

    Examples:
        >>> from typing import Annotated
        >>> from dataclasses import dataclass
        >>> from spakky.plugins.sqlalchemy.orm.relationships import OneToMany
        >>> from spakky.plugins.sqlalchemy.orm.table import Table
        >>>
        >>> @Table()
        >>> @dataclass
        >>> class Order:
        ...     # Bidirectional: Order has many OrderItems
        ...     items: Annotated[list[OrderItem], OneToMany(back_populates="order")]
        >>>
        >>> @Table()
        >>> @dataclass
        >>> class Category:
        ...     # Unidirectional: Category has many Products
        ...     products: Annotated[list[Product], OneToMany()]
        >>>
        >>> @Table()
        >>> @dataclass
        >>> class User:
        ...     # With custom loading strategy
        ...     posts: Annotated[set[Post], OneToMany(back_populates="author", lazy="selectin")]
    """

    cascade: str = "all, delete-orphan"
    """Cascade operations to apply to related objects.

    Common values:
    - "all, delete-orphan": All operations including orphan deletion (default)
    - "save-update, merge": Only persist and merge
    - "delete": Delete related when parent deleted
    - "none": No cascading
    """

    order_by: str | None = None
    """Column name or expression to order the collection by.

    Example: "created_at.desc()" or "name"
    """

    @property
    def relation_type(self) -> RelationType:
        """Get the relationship type.

        Returns:
            RelationType.ONE_TO_MANY
        """
        return RelationType.ONE_TO_MANY
