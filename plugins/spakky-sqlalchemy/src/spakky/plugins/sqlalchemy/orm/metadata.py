"""ORM metadata for SQLAlchemy field-level customization.

This module provides the Field metadata hierarchy for use with typing.Annotated
to customize SQLAlchemy field mapping behavior in a type-safe way.
"""

from dataclasses import dataclass

from spakky.core.common.metadata import AbstractMetadata


@dataclass
class Field(AbstractMetadata):
    """Base metadata class for common field options.

    This class provides common options shared by all field types,
    such as indexing and comments. Subclasses add type-specific options.

    Note:
        Default values should be set using dataclasses.field() or direct assignment,
        not through this metadata. This metadata is for database schema configuration only.

    Attributes:
        index: Whether to create an index on this column.
        unique: Whether to create a unique constraint/index on this column.
        index_name: Optional custom name for the index.
        comment: Optional comment/description for the column.
    """

    index: bool = False
    """Whether to create an index on this column."""

    unique: bool = False
    """Whether to create a unique constraint/index on this column."""

    index_name: str | None = None
    """Optional custom name for the index. Auto-generated if not provided."""

    comment: str | None = None
    """Optional comment/description for the column."""


@dataclass
class StringField(Field):
    """Metadata for string columns with length constraint (VARCHAR).

    Example:
        >>> from typing import Annotated
        >>> from spakky.plugins.sqlalchemy.orm import Table, StringField
        >>>
        >>> @Table()
        >>> class User:
        >>>     email: Annotated[str, StringField(255, unique=True)]
        >>>     username: Annotated[str, StringField(50, index=True)]
        >>>     bio: Annotated[str | None, StringField(1000, comment="User bio")]
    """

    max_length: int = 255
    """Maximum length of the string column."""

    def __post_init__(self) -> None:
        """Validate that max_length is positive."""
        if self.max_length <= 0:
            raise ValueError(f"max_length must be positive, got {self.max_length}")


@dataclass
class DecimalField(Field):
    """Metadata for decimal/numeric columns with precision and scale.

    Example:
        >>> from typing import Annotated
        >>> from decimal import Decimal
        >>> from spakky.plugins.sqlalchemy.orm import Table, DecimalField
        >>>
        >>> @Table()
        >>> class Product:
        >>>     price: Annotated[Decimal, DecimalField(10, 2)]
        >>>     weight: Annotated[Decimal, DecimalField(8, 3, index=True)]
    """

    precision: int = 10
    """Total number of digits (before and after decimal point)."""

    scale: int = 2
    """Number of digits after the decimal point."""

    def __post_init__(self) -> None:
        """Validate precision and scale values."""
        if self.precision <= 0:
            raise ValueError(f"precision must be positive, got {self.precision}")
        if self.scale < 0:
            raise ValueError(f"scale must be non-negative, got {self.scale}")
        if self.scale > self.precision:
            raise ValueError(
                f"scale ({self.scale}) cannot be greater than precision ({self.precision})"
            )


@dataclass
class TextField(Field):
    """Metadata for large text columns (TEXT, CLOB).

    Use this for text that exceeds typical VARCHAR limits or when you don't want
    a length constraint.

    Example:
        >>> from typing import Annotated
        >>> from spakky.plugins.sqlalchemy.orm import Table, TextField
        >>>
        >>> @Table()
        >>> class Article:
        >>>     content: Annotated[str, TextField()]
        >>>     summary: Annotated[str | None, TextField(comment="Brief summary")]
    """


@dataclass
class BinaryField(Field):
    """Metadata for binary data columns (BLOB, BYTEA).

    Example:
        >>> from typing import Annotated
        >>> from spakky.plugins.sqlalchemy.orm import Table, BinaryField
        >>>
        >>> @Table()
        >>> class Document:
        >>>     content: Annotated[bytes, BinaryField()]
        >>>     thumbnail: Annotated[bytes | None, BinaryField(max_length=65536)]
    """

    max_length: int | None = None
    """Maximum length in bytes. None means unlimited (BLOB)."""

    def __post_init__(self) -> None:
        """Validate that max_length is positive if specified."""
        if self.max_length is not None and self.max_length <= 0:
            raise ValueError(f"max_length must be positive, got {self.max_length}")


@dataclass
class EnumField(Field):
    """Metadata for enum columns.

    By default, uses non-native enum (stored as VARCHAR) for better portability.

    Example:
        >>> from typing import Annotated
        >>> from enum import Enum
        >>> from spakky.plugins.sqlalchemy.orm import Table, EnumField
        >>>
        >>> class Status(Enum):
        >>>     ACTIVE = "active"
        >>>     INACTIVE = "inactive"
        >>>
        >>> @Table()
        >>> class User:
        >>>     status: Annotated[Status, EnumField()]
        >>>     role: Annotated[Role, EnumField(native=True)]  # Use DB native enum
    """

    native: bool = False
    """Whether to use database-native enum type. False uses VARCHAR."""


@dataclass
class JsonField(Field):
    """Metadata for JSON/JSONB columns.

    Example:
        >>> from typing import Annotated
        >>> from spakky.plugins.sqlalchemy.orm import Table, JsonField
        >>>
        >>> @Table()
        >>> class Config:
        >>>     settings: Annotated[dict, JsonField()]
        >>>     metadata: Annotated[dict | None, JsonField(binary=True)]  # JSONB
    """

    binary: bool = False
    """Whether to use binary JSON format (JSONB in PostgreSQL)."""


@dataclass
class DateTimeField(Field):
    """Metadata for datetime columns with timezone handling.

    Example:
        >>> from typing import Annotated
        >>> from datetime import datetime
        >>> from spakky.plugins.sqlalchemy.orm import Table, DateTimeField
        >>>
        >>> @Table()
        >>> class Event:
        >>>     created_at: Annotated[datetime, DateTimeField(timezone=True)]
        >>>     scheduled_at: Annotated[datetime | None, DateTimeField()]
    """

    timezone: bool = False
    """Whether to store timezone information."""
