"""Tests for Extractor class."""

import datetime
import decimal
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated, Any, ClassVar

import pytest

from spakky.plugins.sqlalchemy.orm.constraints.index import Index
from spakky.plugins.sqlalchemy.orm.constraints.primary_key import PrimaryKey
from spakky.plugins.sqlalchemy.orm.constraints.unique import Unique
from spakky.plugins.sqlalchemy.orm.extractor import (
    ColumnInfo,
    Extractor,
    MissingRelationshipAnnotationError,
    ModelInfo,
    TableDefinitionNotFoundError,
)
from spakky.plugins.sqlalchemy.orm.fields.binary import Binary
from spakky.plugins.sqlalchemy.orm.fields.boolean import Boolean
from spakky.plugins.sqlalchemy.orm.fields.datetime import Date, DateTime, Time
from spakky.plugins.sqlalchemy.orm.fields.enum import EnumField
from spakky.plugins.sqlalchemy.orm.fields.json import JSON
from spakky.plugins.sqlalchemy.orm.fields.numeric import Float, Integer, Numeric
from spakky.plugins.sqlalchemy.orm.fields.string import String
from spakky.plugins.sqlalchemy.orm.fields.uuid import Uuid
from spakky.plugins.sqlalchemy.orm.relationships.one_to_many import OneToMany
from spakky.plugins.sqlalchemy.orm.table import Table


class UserRole(Enum):
    """Sample enum for testing."""

    ADMIN = "admin"
    USER = "user"


def test_extract_without_table_annotation_expect_error() -> None:
    """Table annotation이 없는 클래스에서 추출 시 TableDefinitionNotFoundError가 발생하는지 검증한다."""

    @dataclass
    class NoTableEntity:
        id: int

    extractor = Extractor()
    with pytest.raises(TableDefinitionNotFoundError):
        extractor.extract(NoTableEntity)


def test_extract_with_annotated_fields_expect_correct_metadata() -> None:
    """Annotated 타입의 필드에서 메타데이터가 올바르게 추출되는지 검증한다."""

    @Table(table_name="users")
    @dataclass
    class User:
        id: Annotated[int, Integer(), PrimaryKey()]
        name: Annotated[str, String(length=100)]

    extractor = Extractor()
    result = extractor.extract(User)

    assert result.table_name == "users"
    assert "id" in result.columns
    assert "name" in result.columns

    id_col = result.columns["id"]
    assert isinstance(id_col.field_metadata, Integer)
    assert len(id_col.constraints) == 1
    assert isinstance(id_col.constraints[0], PrimaryKey)
    assert id_col.nullable is False

    name_col = result.columns["name"]
    assert isinstance(name_col.field_metadata, String)
    assert name_col.field_metadata.length == 100
    assert name_col.nullable is False


def test_extract_with_non_annotated_fields_expect_inferred_types() -> None:
    """Annotated가 아닌 필드에서 타입이 자동 추론되는지 검증한다."""

    @Table()
    @dataclass
    class SimpleEntity:
        id: int
        name: str

    extractor = Extractor()
    result = extractor.extract(SimpleEntity)

    assert isinstance(result.columns["id"].field_metadata, Integer)
    assert isinstance(result.columns["name"].field_metadata, String)


def test_extract_with_optional_fields_expect_nullable_true() -> None:
    """Optional 타입 필드가 nullable=True로 추출되는지 검증한다."""

    @Table()
    @dataclass
    class EntityWithOptional:
        required_field: int
        optional_field: int | None = None

    extractor = Extractor()
    result = extractor.extract(EntityWithOptional)

    assert result.columns["required_field"].nullable is False
    assert result.columns["optional_field"].nullable is True


def test_extract_with_annotated_optional_fields_expect_nullable_true() -> None:
    """Annotated + Optional 타입 필드가 nullable=True로 추출되는지 검증한다."""

    @Table()
    @dataclass
    class EntityWithAnnotatedOptional:
        name: Annotated[str | None, String(length=50)] = None

    extractor = Extractor()
    result = extractor.extract(EntityWithAnnotatedOptional)

    assert result.columns["name"].nullable is True
    assert result.columns["name"].python_type is str


def test_extract_with_multiple_constraints_expect_all_extracted() -> None:
    """여러 제약 조건이 모두 추출되는지 검증한다."""

    @Table()
    @dataclass
    class EntityWithConstraints:
        email: Annotated[str, String(length=255), Unique(), Index()]

    extractor = Extractor()
    result = extractor.extract(EntityWithConstraints)

    email_col = result.columns["email"]
    assert len(email_col.constraints) == 2
    constraint_types = {type(c) for c in email_col.constraints}
    assert Unique in constraint_types
    assert Index in constraint_types


def test_extract_with_default_value_expect_default_preserved() -> None:
    """default 값이 올바르게 추출되는지 검증한다."""

    @Table()
    @dataclass
    class EntityWithDefault:
        status: str = "active"

    extractor = Extractor()
    result = extractor.extract(EntityWithDefault)

    assert result.columns["status"].default == "active"


def test_extract_with_default_factory_expect_factory_preserved() -> None:
    """default_factory가 올바르게 추출되는지 검증한다."""

    @Table()
    @dataclass
    class EntityWithFactory:
        tags: list[str] = field(default_factory=list)

    extractor = Extractor()
    result = extractor.extract(EntityWithFactory)

    assert result.columns["tags"].default_factory is list


def test_extract_with_no_default_expect_none() -> None:
    """default가 없는 필드에서 default=None으로 추출되는지 검증한다."""

    @Table()
    @dataclass
    class EntityNoDefault:
        id: int

    extractor = Extractor()
    result = extractor.extract(EntityNoDefault)

    assert result.columns["id"].default is None
    assert result.columns["id"].default_factory is None


def test_extract_ignores_class_variables() -> None:
    """dataclass 필드가 아닌 클래스 변수는 무시되는지 검증한다."""

    @Table()
    @dataclass
    class EntityWithClassVar:
        id: int
        class_var: int = field(init=False, default=0)

    extractor = Extractor()
    result = extractor.extract(EntityWithClassVar)

    # class_var는 dataclass field이므로 포함됨
    assert "id" in result.columns
    assert "class_var" in result.columns


def test_infer_field_type_int_expect_integer() -> None:
    """int 타입이 Integer로 추론되는지 검증한다."""

    @Table()
    @dataclass
    class Entity:
        value: int

    extractor = Extractor()
    result = extractor.extract(Entity)

    assert isinstance(result.columns["value"].field_metadata, Integer)


def test_infer_field_type_float_expect_float() -> None:
    """float 타입이 Float로 추론되는지 검증한다."""

    @Table()
    @dataclass
    class Entity:
        value: float

    extractor = Extractor()
    result = extractor.extract(Entity)

    assert isinstance(result.columns["value"].field_metadata, Float)


def test_infer_field_type_str_expect_string() -> None:
    """str 타입이 String으로 추론되는지 검증한다."""

    @Table()
    @dataclass
    class Entity:
        value: str

    extractor = Extractor()
    result = extractor.extract(Entity)

    assert isinstance(result.columns["value"].field_metadata, String)


def test_infer_field_type_bool_expect_boolean() -> None:
    """bool 타입이 Boolean으로 추론되는지 검증한다."""

    @Table()
    @dataclass
    class Entity:
        value: bool

    extractor = Extractor()
    result = extractor.extract(Entity)

    assert isinstance(result.columns["value"].field_metadata, Boolean)


def test_infer_field_type_datetime_expect_datetime() -> None:
    """datetime.datetime 타입이 DateTime으로 추론되는지 검증한다."""

    @Table()
    @dataclass
    class Entity:
        value: datetime.datetime

    extractor = Extractor()
    result = extractor.extract(Entity)

    assert isinstance(result.columns["value"].field_metadata, DateTime)


def test_infer_field_type_date_expect_date() -> None:
    """datetime.date 타입이 Date로 추론되는지 검증한다."""

    @Table()
    @dataclass
    class Entity:
        value: datetime.date

    extractor = Extractor()
    result = extractor.extract(Entity)

    assert isinstance(result.columns["value"].field_metadata, Date)


def test_infer_field_type_time_expect_time() -> None:
    """datetime.time 타입이 Time으로 추론되는지 검증한다."""

    @Table()
    @dataclass
    class Entity:
        value: datetime.time

    extractor = Extractor()
    result = extractor.extract(Entity)

    assert isinstance(result.columns["value"].field_metadata, Time)


def test_infer_field_type_uuid_expect_uuid() -> None:
    """uuid.UUID 타입이 Uuid로 추론되는지 검증한다."""

    @Table()
    @dataclass
    class Entity:
        value: uuid.UUID

    extractor = Extractor()
    result = extractor.extract(Entity)

    assert isinstance(result.columns["value"].field_metadata, Uuid)


def test_infer_field_type_decimal_expect_numeric() -> None:
    """decimal.Decimal 타입이 Numeric으로 추론되는지 검증한다."""

    @Table()
    @dataclass
    class Entity:
        value: decimal.Decimal

    extractor = Extractor()
    result = extractor.extract(Entity)

    assert isinstance(result.columns["value"].field_metadata, Numeric)


def test_infer_field_type_bytes_expect_binary() -> None:
    """bytes 타입이 Binary로 추론되는지 검증한다."""

    @Table()
    @dataclass
    class Entity:
        value: bytes

    extractor = Extractor()
    result = extractor.extract(Entity)

    assert isinstance(result.columns["value"].field_metadata, Binary)


def test_infer_field_type_dict_expect_json() -> None:
    """dict 타입이 JSON으로 추론되는지 검증한다."""

    @Table()
    @dataclass
    class Entity:
        value: dict[str, Any]

    extractor = Extractor()
    result = extractor.extract(Entity)

    assert isinstance(result.columns["value"].field_metadata, JSON)


def test_infer_field_type_list_expect_json() -> None:
    """list 타입이 JSON으로 추론되는지 검증한다."""

    @Table()
    @dataclass
    class Entity:
        value: list[int]

    extractor = Extractor()
    result = extractor.extract(Entity)

    assert isinstance(result.columns["value"].field_metadata, JSON)


def test_infer_field_type_plain_dict_expect_json() -> None:
    """제네릭이 아닌 dict 타입이 JSON으로 추론되는지 검증한다."""

    @Table()
    @dataclass
    class Entity:
        value: dict  # type: ignore[type-arg]

    extractor = Extractor()
    result = extractor.extract(Entity)

    assert isinstance(result.columns["value"].field_metadata, JSON)


def test_infer_field_type_plain_list_expect_json() -> None:
    """제네릭이 아닌 list 타입이 JSON으로 추론되는지 검증한다."""

    @Table()
    @dataclass
    class Entity:
        value: list  # type: ignore[type-arg]

    extractor = Extractor()
    result = extractor.extract(Entity)

    assert isinstance(result.columns["value"].field_metadata, JSON)


def test_infer_field_type_enum_expect_enum_field() -> None:
    """Enum 서브클래스가 EnumField로 추론되는지 검증한다."""

    @Table()
    @dataclass
    class Entity:
        role: UserRole

    extractor = Extractor()
    result = extractor.extract(Entity)

    field_meta = result.columns["role"].field_metadata
    assert isinstance(field_meta, EnumField)
    assert field_meta.enum_class is UserRole


def test_infer_field_type_unknown_expect_string_fallback() -> None:
    """알 수 없는 타입이 String으로 폴백되는지 검증한다."""

    class CustomClass:
        pass

    @Table()
    @dataclass
    class Entity:
        value: CustomClass

    extractor = Extractor()
    result = extractor.extract(Entity)

    assert isinstance(result.columns["value"].field_metadata, String)


def test_model_info_structure() -> None:
    """ModelInfo 데이터 클래스 구조가 올바른지 검증한다."""

    @Table(table_name="test_table")
    @dataclass
    class TestEntity:
        id: int

    extractor = Extractor()
    result = extractor.extract(TestEntity)

    assert isinstance(result, ModelInfo)
    assert result.table_name == "test_table"
    assert isinstance(result.columns, dict)


def test_column_info_structure() -> None:
    """ColumnInfo 데이터 클래스 구조가 올바른지 검증한다."""

    @Table()
    @dataclass
    class TestEntity:
        id: Annotated[int, Integer(), PrimaryKey()]

    extractor = Extractor()
    result = extractor.extract(TestEntity)

    col = result.columns["id"]
    assert isinstance(col, ColumnInfo)
    assert col.name == "id"
    assert col.python_type is int
    assert isinstance(col.field_metadata, Integer)
    assert isinstance(col.constraints, list)


def test_extract_preserves_python_type() -> None:
    """python_type이 올바르게 보존되는지 검증한다."""

    @Table()
    @dataclass
    class Entity:
        int_field: int
        str_field: str
        optional_field: int | None = None

    extractor = Extractor()
    result = extractor.extract(Entity)

    assert result.columns["int_field"].python_type is int
    assert result.columns["str_field"].python_type is str
    # Optional에서 None이 제거된 타입
    assert result.columns["optional_field"].python_type is int


def test_extract_skips_class_var_type_hints() -> None:
    """ClassVar로 선언된 타입 힌트는 컬럼으로 추출되지 않는지 검증한다."""

    @Table()
    @dataclass
    class EntityWithClassVar:
        id: int
        class_constant: ClassVar[str] = "constant"

    extractor = Extractor()
    result = extractor.extract(EntityWithClassVar)

    assert "id" in result.columns
    assert "class_constant" not in result.columns


def test_extract_skips_private_fields() -> None:
    """private 필드(_로 시작)가 컬럼으로 추출되지 않는지 검증한다."""

    @Table()
    @dataclass
    class EntityWithPrivateFields:
        id: int
        name: str
        _internal: str = ""
        _events: list[str] = field(default_factory=list)

    extractor = Extractor()
    result = extractor.extract(EntityWithPrivateFields)

    assert "id" in result.columns
    assert "name" in result.columns
    assert "_internal" not in result.columns
    assert "_events" not in result.columns


def test_extract_list_of_table_entity_without_relationship_expect_error() -> None:
    """@Table 엔티티의 list가 relationship 없이 사용되면 오류가 발생하는지 검증한다."""

    @Table(table_name="items")
    @dataclass
    class Item:
        id: int

    @Table(table_name="containers")
    @dataclass
    class Container:
        id: int
        items: list[Item]  # OneToMany 없음 - 잠재적 실수

    extractor = Extractor()
    with pytest.raises(MissingRelationshipAnnotationError) as exc_info:
        extractor.extract(Container)

    assert exc_info.value.args == ("items", Item)


def test_extract_set_of_table_entity_without_relationship_expect_error() -> None:
    """@Table 엔티티의 set이 relationship 없이 사용되면 오류가 발생하는지 검증한다."""

    @Table(table_name="tags")
    @dataclass
    class Tag:
        id: int

    @Table(table_name="posts")
    @dataclass
    class Post:
        id: int
        tags: set[Tag]  # OneToMany 없음 - 잠재적 실수

    extractor = Extractor()
    with pytest.raises(MissingRelationshipAnnotationError) as exc_info:
        extractor.extract(Post)

    assert exc_info.value.args == ("tags", Tag)


def test_extract_list_of_non_table_class_expect_json() -> None:
    """@Table이 아닌 클래스의 list는 JSON으로 매핑되는지 검증한다."""

    @dataclass
    class SimpleData:
        value: int

    @Table(table_name="entities")
    @dataclass
    class EntityWithDataList:
        id: int
        data: list[SimpleData]

    extractor = Extractor()
    result = extractor.extract(EntityWithDataList)

    # SimpleData는 @Table이 아니므로 JSON으로 매핑
    assert "data" in result.columns
    assert isinstance(result.columns["data"].field_metadata, JSON)


def test_extract_list_of_primitive_expect_json() -> None:
    """기본 타입의 list는 JSON으로 매핑되는지 검증한다."""

    @Table(table_name="entities")
    @dataclass
    class EntityWithPrimitiveList:
        id: int
        tags: list[str]

    extractor = Extractor()
    result = extractor.extract(EntityWithPrimitiveList)

    assert "tags" in result.columns
    assert isinstance(result.columns["tags"].field_metadata, JSON)


def test_extract_annotated_list_with_explicit_json_expect_no_error() -> None:
    """명시적 JSON 어노테이션이 있는 @Table 엔티티 list는 허용되는지 검증한다."""

    @Table(table_name="items")
    @dataclass
    class Item:
        id: int

    @Table(table_name="containers")
    @dataclass
    class Container:
        id: int
        # 의도적으로 JSON으로 저장 (snapshot 등)
        items_snapshot: Annotated[list[Item], JSON()]

    extractor = Extractor()
    result = extractor.extract(Container)

    # 명시적 JSON 필드 메타데이터가 있으면 오류 없이 처리
    assert "items_snapshot" in result.columns
    assert isinstance(result.columns["items_snapshot"].field_metadata, JSON)


def test_extract_one_to_many_on_non_collection_expect_skipped() -> None:
    """OneToMany가 비컬렉션 타입에 붙은 경우 relation이 추출되지 않는지 검증한다."""

    @Table(table_name="targets")
    @dataclass
    class Target:
        id: int

    @Table(table_name="sources")
    @dataclass
    class Source:
        id: int
        # OneToMany는 collection에만 해당하므로 단일 엔티티에는 무효
        invalid_relation: Annotated[Target, OneToMany(back_populates="source")]

    extractor = Extractor()
    result = extractor.extract(Source)

    # OneToMany가 단일 타입에 붙으면 relation으로 추출되지 않고 무시됨
    assert len(result.relations) == 0
    # column으로도 처리되지 않음 (relationship 필드는 continue로 스킵)
    assert "invalid_relation" not in result.columns


def test_extract_raw_list_without_generic_expect_json() -> None:
    """제네릭 없는 순수 list 타입이 JSON으로 매핑되는지 검증한다."""

    @Table(table_name="entities")
    @dataclass
    class EntityWithRawList:
        id: int
        items: list  # type: ignore[type-arg]  # Intentionally raw list for test

    extractor = Extractor()
    result = extractor.extract(EntityWithRawList)

    assert "items" in result.columns
    assert isinstance(result.columns["items"].field_metadata, JSON)


def test_extract_one_to_many_on_raw_list_expect_skipped() -> None:
    """OneToMany가 제네릭 없는 list에 붙은 경우 relation이 추출되지 않는지 검증한다."""
    from collections.abc import Collection

    @Table(table_name="sources")
    @dataclass
    class Source:
        id: int
        # Collection without type argument
        items: Annotated[Collection, OneToMany()]  # type: ignore[type-arg]

    extractor = Extractor()
    result = extractor.extract(Source)

    # OneToMany가 raw Collection에 붙으면 relation으로 추출되지 않음 (args 없음)
    assert len(result.relations) == 0
