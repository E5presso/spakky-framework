from abc import ABC
from typing import Callable, Generic

from spakky.core.common.metadata import AbstractMetadata
from spakky.core.common.mutability import mutable
from spakky.core.common.types import AnyT


@mutable
class AbstractField(AbstractMetadata, ABC, Generic[AnyT]):
    """Base class for ORM field metadata annotations.

    Provides common field attributes for SQLAlchemy Column mapping.
    Use with constraint metadata (PrimaryKey, Index, Unique, etc.) for full configuration.
    """

    nullable: bool = True
    """Whether the field can be NULL."""

    default: AnyT | None = None
    """Default value for the field."""

    default_factory: Callable[[], AnyT] | None = None
    """Factory function to generate default value for the field."""

    name: str = ""
    """Custom column name in the database (if different from field name)."""

    comment: str | None = None
    """Column comment/documentation in the database."""
