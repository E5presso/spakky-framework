"""Type mapping registry for Python to SQLAlchemy type conversion.

This module provides a TypeMapper class that converts Python types to SQLAlchemy
column types, with support for custom field metadata for additional configuration.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, get_args, get_origin
from uuid import UUID

from spakky.core.common.types import AnyT

from spakky.plugins.sqlalchemy.orm.metadata import (
    BinaryField,
    DateTimeField,
    DecimalField,
    EnumField,
    Field,
    JsonField,
    StringField,
    TextField,
    TimeField,
)
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    Interval,
    LargeBinary,
    Numeric,
    String,
    Text,
    Time,
    Uuid,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON, TypeEngine


class TypeMapper:
    """Maps Python types to SQLAlchemy column types.

    This class provides a clean interface for resolving Python types to their
    corresponding SQLAlchemy column types. Field metadata is extracted directly
    from Annotated type hints.

    Example:
        >>> from typing import Annotated
        >>> mapper = TypeMapper()
        >>> mapper.resolve(str)
        String(length=255)
        >>> mapper.resolve(Annotated[str, StringField(max_length=100)])
        String(length=100)
        >>> mapper.resolve(Annotated[Decimal, DecimalField(precision=15, scale=4)])
        Numeric(precision=15, scale=4)
    """

    # Default configurations
    DEFAULT_STRING_LENGTH: int = 255
    DEFAULT_DECIMAL_PRECISION: int = 10
    DEFAULT_DECIMAL_SCALE: int = 2
    DEFAULT_DATETIME_TIMEZONE: bool = True
    DEFAULT_TIME_TIMEZONE: bool = False

    def resolve(self, python_type: AnyT) -> TypeEngine[AnyT]:
        """Resolve Python type to SQLAlchemy column type.

        Extracts Field metadata from Annotated type hints if present.

        Args:
            python_type: The Python type to convert. Can be a plain type or
                an Annotated type with Field metadata.

        Returns:
            SQLAlchemy TypeEngine instance.
        """
        base_type, metadata = self._extract_type_info(python_type)
        return self._resolve_type(base_type, metadata)

    def _extract_type_info(self, python_type: Any) -> tuple[type, Field | None]:
        """Extract base type and Field metadata from a type annotation.

        Args:
            python_type: Plain type or Annotated type.

        Returns:
            Tuple of (base_type, field_metadata or None).
        """
        origin = get_origin(python_type)
        if origin is None:
            return python_type, None

        # Handle Annotated types
        args = get_args(python_type)
        if not args:
            return python_type, None

        base_type = args[0]
        metadata = next(
            (arg for arg in args[1:] if isinstance(arg, Field)),
            None,
        )
        return base_type, metadata

    def _resolve_type(
        self,
        python_type: type,
        metadata: Field | None,
    ) -> TypeEngine[Any]:
        """Resolve base Python type to SQLAlchemy column type."""
        # Handle generic types (e.g., dict[str, Any] -> dict)
        origin = get_origin(python_type)
        if origin is not None:
            python_type = origin

        match python_type:
            case t if t is str:
                return self._str(metadata)
            case t if t is int:
                return Integer()
            case t if t is float:
                return Float()
            case t if t is bool:
                return Boolean()
            case t if t is bytes:
                return self._bytes(metadata)
            case t if t is Decimal:
                return self._decimal(metadata)
            case t if t is UUID:
                return Uuid()
            case t if t is datetime:
                return self._datetime(metadata)
            case t if t is date:
                return Date()
            case t if t is time:
                return self._time(metadata)
            case t if t is timedelta:
                return Interval()
            case t if t is dict:
                return self._json(metadata)
            case t if issubclass(t, Enum):
                return self._enum(t, metadata)
            case _:
                return String(length=self.DEFAULT_STRING_LENGTH)

    def _str(self, metadata: Field | None) -> TypeEngine[Any]:
        match metadata:
            case TextField():
                return Text()
            case StringField():
                return String(length=metadata.max_length)
            case _:
                return String(length=self.DEFAULT_STRING_LENGTH)

    def _bytes(self, metadata: Field | None) -> TypeEngine[Any]:
        match metadata:
            case BinaryField() if metadata.max_length is not None:
                return LargeBinary(length=metadata.max_length)
            case _:
                return LargeBinary()

    def _decimal(self, metadata: Field | None) -> TypeEngine[Any]:
        match metadata:
            case DecimalField():
                return Numeric(precision=metadata.precision, scale=metadata.scale)
            case _:
                return Numeric(
                    precision=self.DEFAULT_DECIMAL_PRECISION,
                    scale=self.DEFAULT_DECIMAL_SCALE,
                )

    def _datetime(self, metadata: Field | None) -> TypeEngine[Any]:
        match metadata:
            case DateTimeField():
                return DateTime(timezone=metadata.timezone)
            case _:
                return DateTime(timezone=self.DEFAULT_DATETIME_TIMEZONE)

    def _time(self, metadata: Field | None) -> TypeEngine[Any]:
        match metadata:
            case TimeField():
                return Time(timezone=metadata.timezone)
            case _:
                return Time(timezone=self.DEFAULT_TIME_TIMEZONE)

    def _json(self, metadata: Field | None) -> TypeEngine[Any]:
        match metadata:
            case JsonField() if metadata.binary:
                return JSONB()
            case JsonField():
                return JSON()
            case _:
                # dict without explicit JsonField falls back to String
                return String(length=self.DEFAULT_STRING_LENGTH)

    def _enum(
        self,
        python_type: type[Enum],
        metadata: Field | None,
    ) -> TypeEngine[Any]:
        match metadata:
            case EnumField():
                return SAEnum(python_type, native_enum=metadata.native)
            case _:
                return SAEnum(python_type, native_enum=False)
