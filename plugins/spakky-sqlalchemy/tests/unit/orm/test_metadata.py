"""Unit tests for ORM metadata."""

from decimal import Decimal
from typing import Annotated, Any, Union, get_origin

import pytest
from spakky.core.common.metadata import get_metadata

from spakky.plugins.sqlalchemy.orm import (
    BinaryField,
    DateTimeField,
    DecimalField,
    EnumField,
    Field,
    JsonField,
    StringField,
    TextField,
)


def test_field_base_defaults() -> None:
    """Test that Field base class has correct defaults."""
    field = Field()
    assert field.index is False
    assert field.unique is False
    assert field.index_name is None
    assert field.comment is None


def test_field_with_common_options() -> None:
    """Test that Field accepts common options."""
    field = Field(index=True, unique=True, comment="Test comment")
    assert field.index is True
    assert field.unique is True
    assert field.comment == "Test comment"


def test_string_field_with_max_length() -> None:
    """Test that StringField metadata can be extracted."""
    field_type = Annotated[str, StringField(max_length=100)]
    extracted_type, metadata_list = get_metadata(field_type)

    assert extracted_type is str
    assert len(metadata_list) == 1
    assert isinstance(metadata_list[0], StringField)
    assert metadata_list[0].max_length == 100


def test_string_field_with_index() -> None:
    """Test that StringField with index can be extracted."""
    field_type = Annotated[str, StringField(max_length=255, index=True)]
    extracted_type, metadata_list = get_metadata(field_type)

    assert extracted_type is str
    field = metadata_list[0]
    assert isinstance(field, StringField)
    assert field.max_length == 255
    assert field.index is True


def test_string_field_with_unique() -> None:
    """Test that StringField with unique constraint can be extracted."""
    field_type = Annotated[str, StringField(max_length=255, unique=True)]
    extracted_type, metadata_list = get_metadata(field_type)

    assert extracted_type is str
    field = metadata_list[0]
    assert isinstance(field, StringField)
    assert field.max_length == 255
    assert field.unique is True


def test_string_field_with_optional() -> None:
    """Test that StringField works with Optional types."""
    field_type = Annotated[str | None, StringField(max_length=255)]
    extracted_type, metadata_list = get_metadata(field_type)

    assert get_origin(extracted_type) in (Union, type(str | None))
    assert isinstance(metadata_list[0], StringField)
    assert metadata_list[0].max_length == 255


def test_string_field_validation() -> None:
    """Test that StringField validates positive max_length."""
    StringField(max_length=100)  # Should work

    with pytest.raises(ValueError, match="max_length must be positive"):
        StringField(max_length=0)

    with pytest.raises(ValueError, match="max_length must be positive"):
        StringField(max_length=-1)


def test_string_field_inherits_field() -> None:
    """Test that StringField inherits from Field."""
    assert issubclass(StringField, Field)
    field = StringField(max_length=100, unique=True, comment="Email address")
    assert field.max_length == 100
    assert field.unique is True
    assert field.comment == "Email address"


def test_decimal_field_with_precision() -> None:
    """Test that DecimalField metadata can be extracted."""
    field_type = Annotated[Decimal, DecimalField(precision=10, scale=2)]
    extracted_type, metadata_list = get_metadata(field_type)

    assert extracted_type is Decimal
    assert len(metadata_list) == 1
    assert isinstance(metadata_list[0], DecimalField)
    assert metadata_list[0].precision == 10
    assert metadata_list[0].scale == 2


def test_decimal_field_with_index() -> None:
    """Test that DecimalField with index can be extracted."""
    field_type = Annotated[Decimal, DecimalField(precision=8, scale=3, index=True)]
    extracted_type, metadata_list = get_metadata(field_type)

    assert extracted_type is Decimal
    field = metadata_list[0]
    assert isinstance(field, DecimalField)
    assert field.precision == 8
    assert field.scale == 3
    assert field.index is True


def test_decimal_field_validation() -> None:
    """Test that DecimalField validates precision and scale values."""
    DecimalField(precision=10, scale=2)  # Should work
    DecimalField(precision=8, scale=0)  # Should work

    with pytest.raises(ValueError, match="precision must be positive"):
        DecimalField(precision=0, scale=2)

    with pytest.raises(ValueError, match="precision must be positive"):
        DecimalField(precision=-1, scale=2)

    with pytest.raises(ValueError, match="scale must be non-negative"):
        DecimalField(precision=10, scale=-1)

    with pytest.raises(ValueError, match="scale .* cannot be greater than precision"):
        DecimalField(precision=10, scale=11)


def test_decimal_field_inherits_field() -> None:
    """Test that DecimalField inherits from Field."""
    assert issubclass(DecimalField, Field)
    field = DecimalField(precision=10, scale=2, index=True, comment="Price")
    assert field.precision == 10
    assert field.scale == 2
    assert field.index is True
    assert field.comment == "Price"


def test_text_field() -> None:
    """Test that TextField can be extracted."""
    field_type = Annotated[str, TextField()]
    extracted_type, metadata_list = get_metadata(field_type)

    assert extracted_type is str
    assert len(metadata_list) == 1
    assert isinstance(metadata_list[0], TextField)


def test_text_field_inherits_field() -> None:
    """Test that TextField inherits from Field."""
    assert issubclass(TextField, Field)
    field = TextField(comment="Large text content")
    assert field.comment == "Large text content"


def test_binary_field() -> None:
    """Test that BinaryField can be extracted."""
    field_type = Annotated[bytes, BinaryField()]
    extracted_type, metadata_list = get_metadata(field_type)

    assert extracted_type is bytes
    assert len(metadata_list) == 1
    assert isinstance(metadata_list[0], BinaryField)
    assert metadata_list[0].max_length is None


def test_binary_field_with_max_length() -> None:
    """Test that BinaryField with max_length can be extracted."""
    field_type = Annotated[bytes, BinaryField(max_length=65536)]
    extracted_type, metadata_list = get_metadata(field_type)

    assert extracted_type is bytes
    field = metadata_list[0]
    assert isinstance(field, BinaryField)
    assert field.max_length == 65536


def test_binary_field_validation() -> None:
    """Test that BinaryField validates max_length if specified."""
    BinaryField()  # No max_length, should work
    BinaryField(max_length=1000)  # Should work

    with pytest.raises(ValueError, match="max_length must be positive"):
        BinaryField(max_length=0)

    with pytest.raises(ValueError, match="max_length must be positive"):
        BinaryField(max_length=-1)


def test_enum_field() -> None:
    """Test that EnumField can be extracted."""
    from enum import Enum

    class Status(Enum):
        ACTIVE = "active"

    field_type = Annotated[Status, EnumField()]
    extracted_type, metadata_list = get_metadata(field_type)

    assert extracted_type is Status
    assert len(metadata_list) == 1
    assert isinstance(metadata_list[0], EnumField)
    assert metadata_list[0].native is False


def test_enum_field_native() -> None:
    """Test that EnumField with native=True can be extracted."""
    from enum import Enum

    class Status(Enum):
        ACTIVE = "active"

    field_type = Annotated[Status, EnumField(native=True)]
    extracted_type, metadata_list = get_metadata(field_type)

    field = metadata_list[0]
    assert isinstance(field, EnumField)
    assert field.native is True


def test_json_field() -> None:
    """Test that JsonField can be extracted."""
    field_type = Annotated[dict[str, Any], JsonField()]
    extracted_type, metadata_list = get_metadata(field_type)

    assert get_origin(extracted_type) is dict
    assert len(metadata_list) == 1
    assert isinstance(metadata_list[0], JsonField)
    assert metadata_list[0].binary is False


def test_json_field_binary() -> None:
    """Test that JsonField with binary=True (JSONB) can be extracted."""
    field_type = Annotated[dict[str, Any], JsonField(binary=True)]
    extracted_type, metadata_list = get_metadata(field_type)

    field = metadata_list[0]
    assert isinstance(field, JsonField)
    assert field.binary is True


def test_datetime_field() -> None:
    """Test that DateTimeField can be extracted."""
    from datetime import datetime

    field_type = Annotated[datetime, DateTimeField()]
    extracted_type, metadata_list = get_metadata(field_type)

    assert extracted_type is datetime
    assert len(metadata_list) == 1
    assert isinstance(metadata_list[0], DateTimeField)
    assert metadata_list[0].timezone is False


def test_datetime_field_with_timezone() -> None:
    """Test that DateTimeField with timezone=True can be extracted."""
    from datetime import datetime

    field_type = Annotated[datetime, DateTimeField(timezone=True)]
    extracted_type, metadata_list = get_metadata(field_type)

    field = metadata_list[0]
    assert isinstance(field, DateTimeField)
    assert field.timezone is True
