"""Base class for relationship metadata annotations."""

from abc import ABC
from enum import Enum, auto

from spakky.core.common.metadata import AbstractMetadata
from spakky.core.common.mutability import mutable


class RelationType(Enum):
    """Relationship type enumeration.

    Defines the cardinality of relationships between entities.
    """

    ONE_TO_ONE = auto()
    """One entity has exactly one related entity (single reference, uselist=False)."""

    ONE_TO_MANY = auto()
    """One entity has many related entities (collection)."""

    MANY_TO_ONE = auto()
    """Many entities reference one entity (single reference)."""


@mutable
class AbstractRelationship(AbstractMetadata, ABC):
    """Base class for ORM relationship metadata annotations.

    Provides common attributes for SQLAlchemy relationship mapping.
    Use in Annotated type hints to define entity relationships.

    Examples:
        >>> from typing import Annotated
        >>> from spakky.plugins.sqlalchemy.orm.relationships import OneToMany, ManyToOne
        >>>
        >>> @Table()
        >>> @dataclass
        >>> class Order:
        ...     items: Annotated[list[OrderItem], OneToMany(back_populates="order")]
        >>>
        >>> @Table()
        >>> @dataclass
        >>> class OrderItem:
        ...     order: Annotated[Order, ManyToOne(back_populates="items")]
    """

    back_populates: str | None = None
    """Name of the reverse relationship field on the target entity.

    Used for bidirectional relationships to keep both sides in sync.
    """

    lazy: str = "select"
    """Loading strategy for the relationship.

    Common values:
    - "select": Load on first access (default)
    - "joined": Load in the same query using JOIN
    - "subquery": Load in a separate subquery
    - "selectin": Load using SELECT IN
    - "raise": Raise exception if accessed without explicit loading
    - "noload": Don't load automatically
    """

    @property
    def relation_type(self) -> RelationType:
        """Get the relationship type.

        Returns:
            The RelationType enum value.
        """
        raise NotImplementedError
