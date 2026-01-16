"""ORM annotations for SQLAlchemy entity customization.

This module provides class-level annotations for customizing SQLAlchemy ORM mapping behavior,
such as specifying custom table names.
"""

from dataclasses import dataclass

from spakky.core.common.annotation import ClassAnnotation
from spakky.core.common.types import ObjectT
from spakky.core.utils.casing import pascal_to_snake


@dataclass
class Table(ClassAnnotation):
    """Annotation to specify custom table name for an entity.

    If no name is provided, the table name is automatically generated from
    the entity class name using snake_case convention (e.g., User -> user,
    OrderItem -> order_item).

    Example (auto-generated table name):
        >>> from spakky.domain.models.entity import AbstractEntity
        >>> from spakky.plugins.sqlalchemy.orm import Table
        >>> from uuid import UUID
        >>>
        >>> @Table()
        >>> class User(AbstractEntity[UUID]):
        >>>     name: str
        >>>     email: str
        >>>
        >>> # Table name will be "user"

    Example (custom table name):
        >>> @Table(name="user_accounts")
        >>> class User(AbstractEntity[UUID]):
        >>>     name: str
        >>>     email: str
        >>>
        >>> # Table name will be "user_accounts"
    """

    name: str | None = None
    """The custom table name to use for this entity.
    If None, auto-generated from class name in snake_case."""

    def __call__(self, obj: type[ObjectT]) -> type[ObjectT]:
        if not self.name:
            self.name = pascal_to_snake(obj.__name__)
        return super().__call__(obj)
