"""OneToMany relationship metadata for SQLAlchemy ORM."""

from typing import Generic

from spakky.core.common.mutability import mutable
from spakky.core.common.types import ClassT

from spakky.plugins.sqlalchemy.orm.entity_ref import EntityRef
from spakky.plugins.sqlalchemy.orm.relationships.base import (
    AbstractRelationship,
    RelationType,
)
from spakky.plugins.sqlalchemy.orm.relationships.cascade import CascadeOption


@mutable
class OneToMany(AbstractRelationship[ClassT], Generic[ClassT]):
    """One-to-many relationship metadata.

    Use in Annotated type hints to define a one-to-many relationship
    where one entity has a collection of related entities.

    The field type should be a collection type (list, set, frozenset)
    containing the target entity type.

    Examples:
        >>> from typing import Annotated
        >>> from dataclasses import dataclass
        >>> from spakky.plugins.sqlalchemy.orm.relationships import OneToMany, CascadeOption
        >>> from spakky.plugins.sqlalchemy.orm.relationships.field_ref import FieldRef
        >>> from spakky.plugins.sqlalchemy.orm.table import Table
        >>>
        >>> @Table()
        >>> @dataclass
        >>> class Order:
        ...     # Type-safe with FieldRef and CascadeOption
        ...     items: Annotated[
        ...         list[OrderItem],
        ...         OneToMany(
        ...             back_populates=FieldRef(OrderItem, lambda t: t.order),
        ...             cascade=CascadeOption.ALL | CascadeOption.DELETE_ORPHAN,
        ...             order_by=FieldRef(OrderItem, lambda t: t.created_at),
        ...         )
        ...     ]
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

    cascade: str | CascadeOption = CascadeOption.ALL_DELETE_ORPHAN
    """Cascade operations to apply to related objects.

    Can be specified as:
    - `CascadeOption` flags: Type-safe with `|` operator support
    - `str`: String value for backward compatibility

    Common values:
    - `CascadeOption.ALL_DELETE_ORPHAN`: All operations including orphan deletion (default)
    - `CascadeOption.SAVE_UPDATE | CascadeOption.MERGE`: Only persist and merge
    - `CascadeOption.DELETE`: Delete related when parent deleted
    - `CascadeOption.NONE`: No cascading
    """

    order_by: EntityRef[ClassT] | str | None = None
    """Column to order the collection by.

    Can be specified as:
    - `FieldRef(Entity, lambda t: t.field)`: Type-safe reference with lambda accessor
    - `FieldRef(Entity, "field_name")`: Type-safe reference with string
    - `str`: Column name or expression (e.g., "created_at.desc()")
    - `None`: No ordering (default)
    """

    @property
    def relation_type(self) -> RelationType:
        """Get the relationship type.

        Returns:
            RelationType.ONE_TO_MANY
        """
        return RelationType.ONE_TO_MANY
