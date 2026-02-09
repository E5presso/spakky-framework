"""Type-safe entity field reference for SQLAlchemy ORM.

This module provides a unified reference class for type-safe field/column
references used in relationships and constraints.
"""

from typing import Any, Callable, Generic, cast, overload

from spakky.core.common.types import ClassT
from spakky.core.utils.casing import pascal_to_snake

from spakky.plugins.sqlalchemy.orm.table import Table


class _FieldAccessor:
    """Proxy object to capture field access from lambda expressions.

    Used internally to extract field names from lambda expressions.
    Implements __getattr__ to return the accessed attribute name as string.

    This class is only used at runtime - type hints use `T` for IDE support.
    """

    def __getattr__(self, name: str) -> str:
        """Capture field access and return the field name.

        Args:
            name: The accessed field name.

        Returns:
            The field name as string.
        """
        return name


FieldAccessorCallable = Callable[[_FieldAccessor], str]
"""Internal type alias for runtime field accessor functions."""


class EntityRef(Generic[ClassT]):
    """Type-safe reference to a field on an entity.

    Use this class to define type-safe references for:
    - `back_populates` in relationships (OneToMany, ManyToOne, OneToOne)
    - `column` in ForeignKey constraints
    - `order_by` in OneToMany relationships

    Field specification rules:
    - Type-based entity: Use lambda accessor for IDE autocompletion
        `EntityRef(User, lambda t: t.id)`
    - Forward references (string entity): Use string field name
        `EntityRef("User", "id")`

    Examples:
        >>> from typing import Annotated
        >>> from dataclasses import dataclass
        >>> from spakky.plugins.sqlalchemy.orm.entity_ref import EntityRef
        >>> from spakky.plugins.sqlalchemy.orm.constraints import ForeignKey
        >>> from spakky.plugins.sqlalchemy.orm.relationships import OneToMany, ManyToOne
        >>> from spakky.plugins.sqlalchemy.orm.table import Table
        >>>
        >>> @Table()
        >>> @dataclass
        >>> class User:
        ...     id: Annotated[UUID, Uuid(), PrimaryKey()]
        ...     # Type-safe: references Post.author field
        ...     posts: Annotated[
        ...         list[Post],
        ...         OneToMany(back_populates=EntityRef(Post, lambda t: t.author))
        ...     ]
        >>>
        >>> @Table()
        >>> @dataclass
        >>> class Post:
        ...     # Type-safe: references User.id column
        ...     user_id: Annotated[
        ...         UUID,
        ...         Uuid(),
        ...         ForeignKey(EntityRef(User, lambda t: t.id))
        ...     ]
        ...     # Type-safe: references User.posts field
        ...     author: Annotated[
        ...         User,
        ...         ManyToOne(back_populates=EntityRef(User, lambda t: t.posts))
        ...     ]
    """

    entity: ClassT | str
    """The target entity class or its name (for forward references)."""

    _field_accessor: str | Callable[[ClassT], Any]
    """The field accessor (string or lambda). Lambda provides IDE autocompletion."""

    @overload
    def __init__(
        self,
        entity: ClassT,
        field: Callable[[ClassT], Any],
    ) -> None: ...

    @overload
    def __init__(
        self,
        entity: str,
        field: str,
    ) -> None: ...

    def __init__(
        self,
        entity: ClassT | str,
        field: str | Callable[[ClassT], Any],
    ) -> None:
        """Initialize an entity reference.

        Args:
            entity: The target entity class or its name (string for forward refs).
            field: The field name or lambda accessor (e.g., `lambda t: t.id`).
        """
        self.entity = entity
        self._field_accessor = field

    @property
    def name(self) -> str:
        """Get the field name.

        Returns:
            The field name as string.
        """
        if isinstance(self._field_accessor, str):
            return self._field_accessor
        # Cast for runtime: IDE sees Callable[[T], object], runtime uses _FieldAccessor
        accessor = cast(FieldAccessorCallable, self._field_accessor)
        return accessor(_FieldAccessor())

    @property
    def field_name(self) -> str:
        """Alias for `name` property (backward compatibility).

        Returns:
            The field name as string.
        """
        return self.name

    @property
    def column_name(self) -> str:
        """Alias for `name` property (semantic alias for FK columns).

        Returns:
            The column name as string.
        """
        return self.name

    @property
    def entity_name(self) -> str:
        """Get the entity name as string.

        Returns:
            The entity class name.
        """
        if isinstance(self.entity, str):
            return self.entity
        # At this point, entity is a class, not a string
        return cast(type, self.entity).__name__

    @property
    def table_name(self) -> str:
        """Get the table name from @Table annotation or derive from entity name.

        If the entity class has a @Table annotation with an explicit table_name,
        that value is used. Otherwise, the entity name is converted to snake_case.

        Returns:
            The table name.
        """
        if isinstance(self.entity, str):
            return pascal_to_snake(self.entity)

        # Try to get table name from @Table annotation
        table_metadata: Table | None = Table.get_or_none(self.entity)
        if table_metadata is not None and table_metadata.table_name:
            return table_metadata.table_name

        return pascal_to_snake(self.entity_name)

    def to_fk_string(self) -> str:
        """Convert to SQLAlchemy ForeignKey column string format.

        Returns:
            Column reference string in 'table.column' format.
        """
        return f"{self.table_name}.{self.name}"

    def __repr__(self) -> str:
        """Return string representation.

        Returns:
            String representation of the entity reference.
        """
        return f"EntityRef({self.entity_name}, {self.name!r})"
