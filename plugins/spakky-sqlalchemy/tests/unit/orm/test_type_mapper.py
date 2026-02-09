"""Tests for TypeMapper class."""

import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

import pytest
from spakky.core.common.mutability import mutable
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    Interval,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Uuid as SAUuid

from spakky.plugins.sqlalchemy.orm.constraints.foreign_key import (
    ForeignKey,
    ReferentialAction,
)
from spakky.plugins.sqlalchemy.orm.constraints.index import Index
from spakky.plugins.sqlalchemy.orm.constraints.primary_key import PrimaryKey
from spakky.plugins.sqlalchemy.orm.constraints.unique import Unique
from spakky.plugins.sqlalchemy.orm.extractor import ColumnInfo
from spakky.plugins.sqlalchemy.orm.fields.base import AbstractField
from spakky.plugins.sqlalchemy.orm.fields.binary import Binary
from spakky.plugins.sqlalchemy.orm.fields.boolean import Boolean as BooleanField
from spakky.plugins.sqlalchemy.orm.fields.datetime import (
    Date as DateField,
)
from spakky.plugins.sqlalchemy.orm.fields.datetime import (
    DateTime as DateTimeField,
)
from spakky.plugins.sqlalchemy.orm.fields.datetime import (
    Interval as IntervalField,
)
from spakky.plugins.sqlalchemy.orm.fields.datetime import (
    Time as TimeField,
)
from spakky.plugins.sqlalchemy.orm.fields.enum import EnumField
from spakky.plugins.sqlalchemy.orm.fields.json import JSON as JSONField
from spakky.plugins.sqlalchemy.orm.fields.numeric import (
    BigInteger as BigIntegerField,
)
from spakky.plugins.sqlalchemy.orm.fields.numeric import (
    Float as FloatField,
)
from spakky.plugins.sqlalchemy.orm.fields.numeric import (
    Integer as IntegerField,
)
from spakky.plugins.sqlalchemy.orm.fields.numeric import (
    Numeric as NumericField,
)
from spakky.plugins.sqlalchemy.orm.fields.numeric import (
    SmallInteger as SmallIntegerField,
)
from spakky.plugins.sqlalchemy.orm.fields.string import String as StringField
from spakky.plugins.sqlalchemy.orm.fields.text import Text as TextField
from spakky.plugins.sqlalchemy.orm.fields.uuid import Uuid as UuidField
from spakky.plugins.sqlalchemy.orm.type_mapper import TypeMapper


class Status(Enum):
    """Sample enum for testing."""

    ACTIVE = "active"
    INACTIVE = "inactive"


@pytest.fixture
def type_mapper() -> TypeMapper:
    """Fixture to create a TypeMapper instance."""
    return TypeMapper()


def test_map_integer_field_expect_integer_type(type_mapper: TypeMapper) -> None:
    """Integer 필드가 SQLAlchemy Integer로 매핑되는지 검증한다."""
    col_info = ColumnInfo(
        name="count",
        field_metadata=IntegerField(),
        constraints=[],
        python_type=int,
        nullable=False,
    )

    column = type_mapper.create_column("count", col_info)

    assert isinstance(column.type, Integer)


def test_map_big_integer_field_expect_big_integer_type(type_mapper: TypeMapper) -> None:
    """BigInteger 필드가 SQLAlchemy BigInteger로 매핑되는지 검증한다."""
    col_info = ColumnInfo(
        name="big_count",
        field_metadata=BigIntegerField(),
        constraints=[],
        python_type=int,
        nullable=False,
    )

    column = type_mapper.create_column("big_count", col_info)

    assert isinstance(column.type, BigInteger)


def test_map_small_integer_field_expect_small_integer_type(
    type_mapper: TypeMapper,
) -> None:
    """SmallInteger 필드가 SQLAlchemy SmallInteger로 매핑되는지 검증한다."""
    col_info = ColumnInfo(
        name="small_count",
        field_metadata=SmallIntegerField(),
        constraints=[],
        python_type=int,
        nullable=False,
    )

    column = type_mapper.create_column("small_count", col_info)

    assert isinstance(column.type, SmallInteger)


def test_map_float_field_expect_float_type(type_mapper: TypeMapper) -> None:
    """Float 필드가 SQLAlchemy Float로 매핑되는지 검증한다."""
    col_info = ColumnInfo(
        name="price",
        field_metadata=FloatField(precision=10),
        constraints=[],
        python_type=float,
        nullable=False,
    )

    column = type_mapper.create_column("price", col_info)

    assert isinstance(column.type, Float)


def test_map_numeric_field_expect_numeric_type(type_mapper: TypeMapper) -> None:
    """Numeric 필드가 SQLAlchemy Numeric으로 매핑되는지 검증한다."""
    col_info = ColumnInfo(
        name="amount",
        field_metadata=NumericField(precision=10, scale=2),
        constraints=[],
        python_type=Decimal,
        nullable=False,
    )

    column = type_mapper.create_column("amount", col_info)

    assert isinstance(column.type, Numeric)


def test_map_string_field_expect_string_type(type_mapper: TypeMapper) -> None:
    """String 필드가 SQLAlchemy String으로 매핑되는지 검증한다."""
    col_info = ColumnInfo(
        name="name",
        field_metadata=StringField(length=100),
        constraints=[],
        python_type=str,
        nullable=False,
    )

    column = type_mapper.create_column("name", col_info)

    assert isinstance(column.type, String)
    assert column.type.length == 100


def test_map_text_field_expect_text_type(type_mapper: TypeMapper) -> None:
    """Text 필드가 SQLAlchemy Text로 매핑되는지 검증한다."""
    col_info = ColumnInfo(
        name="content",
        field_metadata=TextField(),
        constraints=[],
        python_type=str,
        nullable=False,
    )

    column = type_mapper.create_column("content", col_info)

    assert isinstance(column.type, Text)


def test_map_boolean_field_expect_boolean_type(type_mapper: TypeMapper) -> None:
    """Boolean 필드가 SQLAlchemy Boolean으로 매핑되는지 검증한다."""
    col_info = ColumnInfo(
        name="is_active",
        field_metadata=BooleanField(),
        constraints=[],
        python_type=bool,
        nullable=False,
    )

    column = type_mapper.create_column("is_active", col_info)

    assert isinstance(column.type, Boolean)


def test_map_date_field_expect_date_type(type_mapper: TypeMapper) -> None:
    """Date 필드가 SQLAlchemy Date로 매핑되는지 검증한다."""
    col_info = ColumnInfo(
        name="birth_date",
        field_metadata=DateField(),
        constraints=[],
        python_type=datetime.date,
        nullable=False,
    )

    column = type_mapper.create_column("birth_date", col_info)

    assert isinstance(column.type, Date)


def test_map_datetime_field_expect_datetime_type(type_mapper: TypeMapper) -> None:
    """DateTime 필드가 SQLAlchemy DateTime으로 매핑되는지 검증한다."""
    col_info = ColumnInfo(
        name="created_at",
        field_metadata=DateTimeField(timezone=True),
        constraints=[],
        python_type=datetime.datetime,
        nullable=False,
    )

    column = type_mapper.create_column("created_at", col_info)

    assert isinstance(column.type, DateTime)
    assert column.type.timezone is True


def test_map_time_field_expect_time_type(type_mapper: TypeMapper) -> None:
    """Time 필드가 SQLAlchemy Time으로 매핑되는지 검증한다."""
    col_info = ColumnInfo(
        name="start_time",
        field_metadata=TimeField(),
        constraints=[],
        python_type=datetime.time,
        nullable=False,
    )

    column = type_mapper.create_column("start_time", col_info)

    assert isinstance(column.type, Time)


def test_map_interval_field_expect_interval_type(type_mapper: TypeMapper) -> None:
    """Interval 필드가 SQLAlchemy Interval로 매핑되는지 검증한다."""
    col_info = ColumnInfo(
        name="duration",
        field_metadata=IntervalField(),
        constraints=[],
        python_type=datetime.timedelta,
        nullable=False,
    )

    column = type_mapper.create_column("duration", col_info)

    assert isinstance(column.type, Interval)


def test_map_uuid_field_expect_uuid_type(type_mapper: TypeMapper) -> None:
    """Uuid 필드가 SQLAlchemy Uuid로 매핑되는지 검증한다."""
    col_info = ColumnInfo(
        name="external_id",
        field_metadata=UuidField(),
        constraints=[],
        python_type=UUID,
        nullable=False,
    )

    column = type_mapper.create_column("external_id", col_info)

    assert isinstance(column.type, SAUuid)


def test_map_json_field_expect_json_type(type_mapper: TypeMapper) -> None:
    """JSON 필드가 SQLAlchemy JSON으로 매핑되는지 검증한다."""
    col_info = ColumnInfo(
        name="metadata",
        field_metadata=JSONField(),
        constraints=[],
        python_type=dict[str, Any],
        nullable=False,
    )

    column = type_mapper.create_column("metadata", col_info)

    assert isinstance(column.type, JSON)


def test_map_binary_field_expect_large_binary_type(type_mapper: TypeMapper) -> None:
    """Binary 필드가 SQLAlchemy LargeBinary로 매핑되는지 검증한다."""
    col_info = ColumnInfo(
        name="data",
        field_metadata=Binary(length=1024),
        constraints=[],
        python_type=bytes,
        nullable=False,
    )

    column = type_mapper.create_column("data", col_info)

    assert isinstance(column.type, LargeBinary)


def test_map_enum_field_expect_enum_type(type_mapper: TypeMapper) -> None:
    """Enum 필드가 SQLAlchemy Enum으로 매핑되는지 검증한다."""
    col_info = ColumnInfo(
        name="status",
        field_metadata=EnumField(enum_class=Status),
        constraints=[],
        python_type=Status,
        nullable=False,
    )

    column = type_mapper.create_column("status", col_info)

    assert isinstance(column.type, SAEnum)


def test_create_column_with_primary_key_expect_primary_key_true(
    type_mapper: TypeMapper,
) -> None:
    """PrimaryKey 제약이 있으면 primary_key가 True인 컬럼이 생성되는지 검증한다."""
    col_info = ColumnInfo(
        name="id",
        field_metadata=IntegerField(),
        constraints=[PrimaryKey()],
        python_type=int,
        nullable=False,
    )

    column = type_mapper.create_column("id", col_info)

    assert column.primary_key is True


def test_create_column_with_unique_expect_unique_true(type_mapper: TypeMapper) -> None:
    """Unique 제약이 있으면 unique가 True인 컬럼이 생성되는지 검증한다."""
    col_info = ColumnInfo(
        name="email",
        field_metadata=StringField(length=255),
        constraints=[Unique()],
        python_type=str,
        nullable=False,
    )

    column = type_mapper.create_column("email", col_info)

    assert column.unique is True


def test_create_column_with_index_expect_index_true(type_mapper: TypeMapper) -> None:
    """Index 제약이 있으면 index가 True인 컬럼이 생성되는지 검증한다."""
    col_info = ColumnInfo(
        name="username",
        field_metadata=StringField(length=50),
        constraints=[Index()],
        python_type=str,
        nullable=False,
    )

    column = type_mapper.create_column("username", col_info)

    assert column.index is True


def test_create_column_with_nullable_expect_nullable_true(
    type_mapper: TypeMapper,
) -> None:
    """nullable이 True이면 nullable 컬럼이 생성되는지 검증한다."""
    col_info = ColumnInfo(
        name="description",
        field_metadata=StringField(length=255),
        constraints=[],
        python_type=str,
        nullable=True,
    )

    column = type_mapper.create_column("description", col_info)

    assert column.nullable is True


def test_create_column_with_default_value_expect_default_set(
    type_mapper: TypeMapper,
) -> None:
    """default 값이 있으면 컬럼에 default가 설정되는지 검증한다."""
    from sqlalchemy import ColumnDefault

    col_info = ColumnInfo(
        name="status",
        field_metadata=StringField(length=20),
        constraints=[],
        python_type=str,
        default="active",
        nullable=False,
    )

    column = type_mapper.create_column("status", col_info)

    assert column.default is not None
    assert isinstance(column.default, ColumnDefault)
    assert column.default.arg == "active"


def test_create_column_with_comment_expect_comment_set(type_mapper: TypeMapper) -> None:
    """comment가 있으면 컬럼에 comment가 설정되는지 검증한다."""
    col_info = ColumnInfo(
        name="name",
        field_metadata=StringField(length=100, comment="User's full name"),
        constraints=[],
        python_type=str,
        nullable=False,
    )

    column = type_mapper.create_column("name", col_info)

    assert column.comment == "User's full name"


def test_create_column_with_custom_column_name_expect_correct_name(
    type_mapper: TypeMapper,
) -> None:
    """커스텀 컬럼명이 있으면 해당 이름으로 컬럼이 생성되는지 검증한다."""
    col_info = ColumnInfo(
        name="user_name",
        field_metadata=StringField(length=100, name="custom_user_name"),
        constraints=[],
        python_type=str,
        nullable=False,
    )

    column = type_mapper.create_column("user_name", col_info)

    assert column.name == "custom_user_name"


def test_create_column_with_foreign_key_expect_foreign_key_constraint(
    type_mapper: TypeMapper,
) -> None:
    """ForeignKey 제약이 있으면 외래키 컬럼이 생성되는지 검증한다."""
    col_info = ColumnInfo(
        name="user_id",
        field_metadata=IntegerField(),
        constraints=[ForeignKey(column="users.id")],
        python_type=int,
        nullable=False,
    )

    column = type_mapper.create_column("user_id", col_info)

    assert len(column.foreign_keys) == 1


def test_create_column_with_foreign_key_cascade_expect_correct_action(
    type_mapper: TypeMapper,
) -> None:
    """ForeignKey에 on_delete CASCADE가 있으면 올바른 액션이 설정되는지 검증한다."""
    col_info = ColumnInfo(
        name="user_id",
        field_metadata=IntegerField(),
        constraints=[
            ForeignKey(column="users.id", on_delete=ReferentialAction.CASCADE)
        ],
        python_type=int,
        nullable=False,
    )

    column = type_mapper.create_column("user_id", col_info)

    fk = list(column.foreign_keys)[0]
    assert fk.ondelete == "CASCADE"


def test_create_column_with_autoincrement_primary_key_expect_autoincrement(
    type_mapper: TypeMapper,
) -> None:
    """PrimaryKey에 autoincrement=True가 있으면 autoincrement가 설정되는지 검증한다."""
    col_info = ColumnInfo(
        name="id",
        field_metadata=IntegerField(),
        constraints=[PrimaryKey(autoincrement=True)],
        python_type=int,
        nullable=False,
    )

    column = type_mapper.create_column("id", col_info)

    assert column.autoincrement is True


def test_create_column_with_unknown_field_type_expect_string_fallback(
    type_mapper: TypeMapper,
) -> None:
    """알 수 없는 필드 타입에 대해 String fallback이 적용되는지 검증한다."""

    @mutable
    class UnknownField(AbstractField[str]):
        """Unknown field type for testing fallback."""

    col_info = ColumnInfo(
        name="custom",
        field_metadata=UnknownField(),
        constraints=[],
        python_type=str,
        nullable=False,
    )

    column = type_mapper.create_column("custom", col_info)

    assert isinstance(column.type, String)
    assert column.type.length == 255  # DEFAULT_STRING_LENGTH
