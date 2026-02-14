"""Tests for ModelRegistry class."""

from dataclasses import dataclass
from typing import Annotated

import pytest
from sqlalchemy import BigInteger, Boolean, String

from spakky.plugins.sqlalchemy.orm.constraints.primary_key import PrimaryKey
from spakky.plugins.sqlalchemy.orm.extractor import Extractor
from spakky.plugins.sqlalchemy.orm.fields.boolean import Boolean as BooleanField
from spakky.plugins.sqlalchemy.orm.fields.numeric import BigInteger as BigIntegerField
from spakky.plugins.sqlalchemy.orm.fields.numeric import Integer as IntegerField
from spakky.plugins.sqlalchemy.orm.fields.string import String as StringField
from spakky.plugins.sqlalchemy.orm.registry import ModelRegistry
from spakky.plugins.sqlalchemy.orm.table import Table
from spakky.plugins.sqlalchemy.orm.type_mapper import TypeMapper


@pytest.fixture
def model_registry() -> ModelRegistry:
    """Fixture to create a ModelRegistry instance."""
    extractor = Extractor()
    type_mapper = TypeMapper()
    return ModelRegistry(extractor=extractor, type_mapper=type_mapper)


def test_register_simple_entity_expect_table_created(
    model_registry: ModelRegistry,
) -> None:
    """간단한 엔티티 클래스를 등록하면 SQLAlchemy Table이 생성되는지 검증한다."""

    @Table()
    @dataclass
    class SimpleEntity:
        id: Annotated[int, IntegerField(), PrimaryKey()]
        name: str

    sa_table = model_registry.register(SimpleEntity)

    assert sa_table is not None
    assert sa_table.name == "simple_entity"
    assert "id" in sa_table.columns
    assert "name" in sa_table.columns


def test_register_entity_with_custom_table_name_expect_correct_name(
    model_registry: ModelRegistry,
) -> None:
    """커스텀 테이블명을 가진 엔티티가 올바른 이름으로 등록되는지 검증한다."""

    @Table(table_name="custom_users")
    @dataclass
    class User:
        id: Annotated[int, IntegerField(), PrimaryKey()]

    sa_table = model_registry.register(User)

    assert sa_table.name == "custom_users"


def test_register_entity_with_various_types_expect_correct_column_types(
    model_registry: ModelRegistry,
) -> None:
    """다양한 필드 타입이 올바른 SQLAlchemy 타입으로 매핑되는지 검증한다."""

    @Table()
    @dataclass
    class TypedEntity:
        id: Annotated[int, BigIntegerField(), PrimaryKey()]
        name: Annotated[str, StringField(length=100)]
        is_active: Annotated[bool, BooleanField()]

    sa_table = model_registry.register(TypedEntity)

    assert isinstance(sa_table.columns["id"].type, BigInteger)
    assert isinstance(sa_table.columns["name"].type, String)
    assert isinstance(sa_table.columns["is_active"].type, Boolean)


def test_is_registered_after_registration_expect_true(
    model_registry: ModelRegistry,
) -> None:
    """등록 후 is_registered가 True를 반환하는지 검증한다."""

    @Table()
    @dataclass
    class TestEntity:
        id: Annotated[int, IntegerField(), PrimaryKey()]

    assert model_registry.is_registered(TestEntity) is False

    model_registry.register(TestEntity)

    assert model_registry.is_registered(TestEntity) is True


def test_get_table_after_registration_expect_table_returned(
    model_registry: ModelRegistry,
) -> None:
    """등록 후 get_table이 올바른 테이블을 반환하는지 검증한다."""

    @Table()
    @dataclass
    class AnotherEntity:
        id: Annotated[int, IntegerField(), PrimaryKey()]

    model_registry.register(AnotherEntity)
    sa_table = model_registry.get_table(AnotherEntity)

    assert sa_table is not None
    assert sa_table.name == "another_entity"


def test_get_table_before_registration_expect_none(
    model_registry: ModelRegistry,
) -> None:
    """등록 전 get_table이 None을 반환하는지 검증한다."""

    @Table()
    @dataclass
    class NotRegisteredEntity:
        id: int

    result = model_registry.get_table(NotRegisteredEntity)

    assert result is None


def test_register_same_entity_twice_expect_same_table_returned(
    model_registry: ModelRegistry,
) -> None:
    """같은 엔티티를 두 번 등록하면 동일한 테이블이 반환되는지 검증한다."""

    @Table()
    @dataclass
    class DuplicateEntity:
        id: Annotated[int, IntegerField(), PrimaryKey()]

    table1 = model_registry.register(DuplicateEntity)
    table2 = model_registry.register(DuplicateEntity)

    assert table1 is table2


def test_registered_entities_property_expect_correct_mapping(
    model_registry: ModelRegistry,
) -> None:
    """registered_entities 프로퍼티가 올바른 매핑을 반환하는지 검증한다."""

    @Table()
    @dataclass
    class Entity1:
        id: Annotated[int, IntegerField(), PrimaryKey()]

    @Table()
    @dataclass
    class Entity2:
        id: Annotated[int, IntegerField(), PrimaryKey()]

    model_registry.register(Entity1)
    model_registry.register(Entity2)

    entities = model_registry.registered_entities

    assert Entity1 in entities
    assert Entity2 in entities
    assert len(entities) == 2


def test_metadata_property_expect_metadata_instance(
    model_registry: ModelRegistry,
) -> None:
    """metadata 프로퍼티가 MetaData 인스턴스를 반환하는지 검증한다."""
    from sqlalchemy import MetaData

    assert isinstance(model_registry.metadata, MetaData)


def test_sqlalchemy_registry_property_expect_registry_instance(
    model_registry: ModelRegistry,
) -> None:
    """sqlalchemy_registry 프로퍼티가 registry 인스턴스를 반환하는지 검증한다."""
    from sqlalchemy.orm import registry

    assert isinstance(model_registry.sqlalchemy_registry, registry)


def test_register_entity_with_nullable_field_expect_nullable_column(
    model_registry: ModelRegistry,
) -> None:
    """Optional 필드가 nullable 컬럼으로 생성되는지 검증한다."""

    @Table()
    @dataclass
    class EntityWithNullable:
        id: Annotated[int, IntegerField(), PrimaryKey()]
        description: str | None = None

    sa_table = model_registry.register(EntityWithNullable)

    assert sa_table.columns["description"].nullable is True


def test_register_entity_with_primary_key_expect_primary_key_column(
    model_registry: ModelRegistry,
) -> None:
    """PrimaryKey 제약이 있는 필드가 primary_key 컬럼으로 생성되는지 검증한다."""

    @Table()
    @dataclass
    class EntityWithPK:
        id: Annotated[int, IntegerField(), PrimaryKey()]
        name: str

    sa_table = model_registry.register(EntityWithPK)

    assert sa_table.columns["id"].primary_key is True
    assert sa_table.columns["name"].primary_key is False


def test_register_entity_with_named_unique_expect_table_level_constraint(
    model_registry: ModelRegistry,
) -> None:
    """Unique(name=...)가 테이블 레벨 UniqueConstraint로 생성되는지 검증한다."""
    from sqlalchemy import UniqueConstraint

    from spakky.plugins.sqlalchemy.orm.constraints.unique import Unique

    @Table(table_name="users_named_unique")
    @dataclass
    class UserWithNamedUnique:
        id: Annotated[int, IntegerField(), PrimaryKey()]
        email: Annotated[str, StringField(length=255), Unique(name="uq_user_email")]

    sa_table = model_registry.register(UserWithNamedUnique)

    # Column-level unique should be None (handled at table level)
    assert sa_table.columns["email"].unique is None

    # Table-level constraint should exist
    constraints = [c for c in sa_table.constraints if isinstance(c, UniqueConstraint)]
    named_constraints = [c for c in constraints if c.name == "uq_user_email"]
    assert len(named_constraints) == 1


def test_register_entity_with_unnamed_unique_expect_column_level(
    model_registry: ModelRegistry,
) -> None:
    """Unique(name 없음)가 컬럼 레벨 unique로 생성되는지 검증한다."""
    from spakky.plugins.sqlalchemy.orm.constraints.unique import Unique

    @Table(table_name="users_unnamed_unique")
    @dataclass
    class UserWithUnnamedUnique:
        id: Annotated[int, IntegerField(), PrimaryKey()]
        email: Annotated[str, StringField(length=255), Unique()]

    sa_table = model_registry.register(UserWithUnnamedUnique)

    # Column-level unique should be True
    assert sa_table.columns["email"].unique is True


def test_register_entity_with_named_index_expect_table_level_index(
    model_registry: ModelRegistry,
) -> None:
    """Index(name=...)가 테이블 레벨 Index로 생성되는지 검증한다."""
    from spakky.plugins.sqlalchemy.orm.constraints.index import Index

    @Table(table_name="products_named_index")
    @dataclass
    class ProductWithNamedIndex:
        id: Annotated[int, IntegerField(), PrimaryKey()]
        sku: Annotated[str, StringField(length=50), Index(name="idx_product_sku")]

    sa_table = model_registry.register(ProductWithNamedIndex)

    # Column-level index should be None (handled at table level)
    assert sa_table.columns["sku"].index is None

    # Table-level index should exist
    indexes = list(sa_table.indexes)
    assert len(indexes) == 1
    assert indexes[0].name == "idx_product_sku"


def test_register_entity_with_unique_index_expect_table_level_unique_index(
    model_registry: ModelRegistry,
) -> None:
    """Index(unique=True)가 테이블 레벨 unique Index로 생성되는지 검증한다."""
    from spakky.plugins.sqlalchemy.orm.constraints.index import Index

    @Table(table_name="products_unique_index")
    @dataclass
    class ProductWithUniqueIndex:
        id: Annotated[int, IntegerField(), PrimaryKey()]
        sku: Annotated[
            str,
            StringField(length=50),
            Index(name="idx_product_sku_unique", unique=True),
        ]

    sa_table = model_registry.register(ProductWithUniqueIndex)

    # Find the index and verify it's unique
    indexes = list(sa_table.indexes)
    assert len(indexes) == 1
    assert indexes[0].unique is True
    assert indexes[0].name == "idx_product_sku_unique"


def test_register_entity_with_unnamed_index_expect_column_level(
    model_registry: ModelRegistry,
) -> None:
    """Index(name 없음, unique=False)가 컬럼 레벨 index로 생성되는지 검증한다."""
    from spakky.plugins.sqlalchemy.orm.constraints.index import Index

    @Table(table_name="products_unnamed_index")
    @dataclass
    class ProductWithUnnamedIndex:
        id: Annotated[int, IntegerField(), PrimaryKey()]
        name: Annotated[str, StringField(length=100), Index()]

    sa_table = model_registry.register(ProductWithUnnamedIndex)

    # Column-level index should be True
    assert sa_table.columns["name"].index is True
