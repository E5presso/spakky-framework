"""Unit tests for TypeMapper."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any
from uuid import UUID

import pytest
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
from sqlalchemy.types import JSON

from spakky.plugins.sqlalchemy.orm import (
    BinaryField,
    DateTimeField,
    DecimalField,
    EnumField,
    JsonField,
    StringField,
    TextField,
    TimeField,
    TypeMapper,
)


class Status(Enum):
    """Test enum for type mapping tests."""

    ACTIVE = "active"
    INACTIVE = "inactive"


@pytest.fixture
def type_mapper() -> TypeMapper:
    """Create a TypeMapper instance for testing."""
    return TypeMapper()


def test_resolve_str_without_metadata(type_mapper: TypeMapper) -> None:
    """Test that str resolves to String(255) by default."""
    result = type_mapper.resolve(str)
    assert isinstance(result, String)
    assert result.length == 255


def test_resolve_str_with_string_field(type_mapper: TypeMapper) -> None:
    """Test that str with StringField uses custom max_length."""
    result = type_mapper.resolve(Annotated[str, StringField(max_length=100)])
    assert isinstance(result, String)
    assert result.length == 100


def test_resolve_str_with_text_field(type_mapper: TypeMapper) -> None:
    """Test that str with TextField resolves to Text."""
    result = type_mapper.resolve(Annotated[str, TextField()])
    assert isinstance(result, Text)


def test_resolve_int(type_mapper: TypeMapper) -> None:
    """Test that int resolves to Integer."""
    result = type_mapper.resolve(int)
    assert isinstance(result, Integer)


def test_resolve_float(type_mapper: TypeMapper) -> None:
    """Test that float resolves to Float."""
    result = type_mapper.resolve(float)
    assert isinstance(result, Float)


def test_resolve_bool(type_mapper: TypeMapper) -> None:
    """Test that bool resolves to Boolean."""
    result = type_mapper.resolve(bool)
    assert isinstance(result, Boolean)


def test_resolve_uuid(type_mapper: TypeMapper) -> None:
    """Test that UUID resolves to Uuid."""
    result = type_mapper.resolve(UUID)
    assert isinstance(result, Uuid)


def test_resolve_datetime_without_metadata(type_mapper: TypeMapper) -> None:
    """Test that datetime resolves to DateTime with timezone=True by default."""
    result = type_mapper.resolve(datetime)
    assert isinstance(result, DateTime)
    assert result.timezone is True


def test_resolve_datetime_with_timezone_false(type_mapper: TypeMapper) -> None:
    """Test that datetime with DateTimeField(timezone=False) works."""
    result = type_mapper.resolve(Annotated[datetime, DateTimeField(timezone=False)])
    assert isinstance(result, DateTime)
    assert result.timezone is False


def test_resolve_datetime_with_timezone_true(type_mapper: TypeMapper) -> None:
    """Test that datetime with DateTimeField(timezone=True) works."""
    result = type_mapper.resolve(Annotated[datetime, DateTimeField(timezone=True)])
    assert isinstance(result, DateTime)
    assert result.timezone is True


def test_resolve_date(type_mapper: TypeMapper) -> None:
    """Test that date resolves to Date."""
    result = type_mapper.resolve(date)
    assert isinstance(result, Date)


def test_resolve_time(type_mapper: TypeMapper) -> None:
    """Test that time resolves to Time."""
    result = type_mapper.resolve(time)
    assert isinstance(result, Time)


def test_resolve_time_with_timezone_false(type_mapper: TypeMapper) -> None:
    """Test that time with TimeField(timezone=False) works."""
    result = type_mapper.resolve(Annotated[time, TimeField(timezone=False)])
    assert isinstance(result, Time)
    assert result.timezone is False


def test_resolve_time_with_timezone_true(type_mapper: TypeMapper) -> None:
    """Test that time with TimeField(timezone=True) works."""
    result = type_mapper.resolve(Annotated[time, TimeField(timezone=True)])
    assert isinstance(result, Time)
    assert result.timezone is True


def test_resolve_timedelta(type_mapper: TypeMapper) -> None:
    """Test that timedelta resolves to Interval."""
    result = type_mapper.resolve(timedelta)
    assert isinstance(result, Interval)


def test_resolve_decimal_without_metadata(type_mapper: TypeMapper) -> None:
    """Test that Decimal resolves to Numeric(10, 2) by default."""
    result = type_mapper.resolve(Decimal)
    assert isinstance(result, Numeric)
    assert result.precision == 10
    assert result.scale == 2


def test_resolve_decimal_with_custom_precision(type_mapper: TypeMapper) -> None:
    """Test that Decimal with DecimalField uses custom precision/scale."""
    result = type_mapper.resolve(
        Annotated[Decimal, DecimalField(precision=15, scale=4)]
    )
    assert isinstance(result, Numeric)
    assert result.precision == 15
    assert result.scale == 4


def test_resolve_bytes_without_metadata(type_mapper: TypeMapper) -> None:
    """Test that bytes resolves to LargeBinary."""
    result = type_mapper.resolve(bytes)
    assert isinstance(result, LargeBinary)


def test_resolve_bytes_with_binary_field(type_mapper: TypeMapper) -> None:
    """Test that bytes with BinaryField and max_length works."""
    result = type_mapper.resolve(Annotated[bytes, BinaryField(max_length=1024)])
    assert isinstance(result, LargeBinary)
    assert result.length == 1024


def test_resolve_bytes_with_binary_field_no_limit(type_mapper: TypeMapper) -> None:
    """Test that bytes with BinaryField without max_length works."""
    result = type_mapper.resolve(Annotated[bytes, BinaryField()])
    assert isinstance(result, LargeBinary)


def test_resolve_dict_without_metadata_fallback(type_mapper: TypeMapper) -> None:
    """Test that dict without JsonField falls back to String (not supported directly)."""
    result = type_mapper.resolve(dict)
    assert isinstance(result, String)
    assert result.length == 255


def test_resolve_dict_with_json_field(type_mapper: TypeMapper) -> None:
    """Test that dict with JsonField resolves to JSON."""
    result = type_mapper.resolve(Annotated[dict[str, Any], JsonField()])
    assert isinstance(result, JSON)


def test_resolve_dict_with_json_field_binary(type_mapper: TypeMapper) -> None:
    """Test that dict with JsonField(binary=True) resolves to JSONB."""
    result = type_mapper.resolve(Annotated[dict[str, Any], JsonField(binary=True)])
    assert isinstance(result, JSONB)


def test_resolve_enum_without_metadata(type_mapper: TypeMapper) -> None:
    """Test that Enum resolves to String by default."""
    result = type_mapper.resolve(Status)
    assert isinstance(result, SAEnum)
    assert result.native_enum is False


def test_resolve_enum_with_enum_field_non_native(type_mapper: TypeMapper) -> None:
    """Test that Enum with EnumField(native=False) resolves to String."""
    result = type_mapper.resolve(Annotated[Status, EnumField(native=False)])
    assert isinstance(result, String)


def test_resolve_enum_with_enum_field_native(type_mapper: TypeMapper) -> None:
    """Test that Enum with EnumField(native=True) uses SQLAlchemy Enum."""
    result = type_mapper.resolve(Annotated[Status, EnumField(native=True)])
    assert isinstance(result, SAEnum)


def test_resolve_unknown_type_fallback(type_mapper: TypeMapper) -> None:
    """Test that unknown types fall back to String(255)."""

    class CustomClass:
        pass

    result = type_mapper.resolve(CustomClass)
    assert isinstance(result, String)
    assert result.length == 255


def test_resolve_list_fallback_to_string(type_mapper: TypeMapper) -> None:
    """Test that list falls back to String (relationship handling in Phase 2)."""
    result = type_mapper.resolve(list)
    assert isinstance(result, String)
    assert result.length == 255
