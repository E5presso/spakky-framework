"""Tests for relationship metadata classes."""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from spakky.plugins.sqlalchemy.orm.constraints.primary_key import PrimaryKey
from spakky.plugins.sqlalchemy.orm.extractor import Extractor
from spakky.plugins.sqlalchemy.orm.fields.uuid import Uuid
from spakky.plugins.sqlalchemy.orm.relationships.base import (
    AbstractRelationship,
    RelationType,
)
from spakky.plugins.sqlalchemy.orm.relationships.many_to_one import ManyToOne
from spakky.plugins.sqlalchemy.orm.relationships.one_to_many import OneToMany
from spakky.plugins.sqlalchemy.orm.relationships.one_to_one import OneToOne
from spakky.plugins.sqlalchemy.orm.table import Table


def test_one_to_many_relation_type_expect_one_to_many() -> None:
    """OneToMany의 relation_type이 ONE_TO_MANY를 반환하는지 검증한다."""
    relation = OneToMany()
    assert relation.relation_type == RelationType.ONE_TO_MANY


def test_many_to_one_relation_type_expect_many_to_one() -> None:
    """ManyToOne의 relation_type이 MANY_TO_ONE을 반환하는지 검증한다."""
    relation = ManyToOne()
    assert relation.relation_type == RelationType.MANY_TO_ONE


def test_one_to_many_default_values_expect_correct_defaults() -> None:
    """OneToMany의 기본값이 올바르게 설정되는지 검증한다."""
    relation = OneToMany()
    assert relation.back_populates is None
    assert relation.lazy == "select"
    assert relation.cascade == "all, delete-orphan"
    assert relation.order_by is None


def test_many_to_one_default_values_expect_correct_defaults() -> None:
    """ManyToOne의 기본값이 올바르게 설정되는지 검증한다."""
    relation = ManyToOne()
    assert relation.back_populates is None
    assert relation.lazy == "select"


def test_one_to_many_with_back_populates_expect_value_preserved() -> None:
    """OneToMany에 back_populates 설정 시 값이 보존되는지 검증한다."""
    relation = OneToMany(back_populates="parent")
    assert relation.back_populates == "parent"


def test_many_to_one_with_back_populates_expect_value_preserved() -> None:
    """ManyToOne에 back_populates 설정 시 값이 보존되는지 검증한다."""
    relation = ManyToOne(back_populates="children")
    assert relation.back_populates == "children"


def test_one_to_many_with_custom_options_expect_values_preserved() -> None:
    """OneToMany에 커스텀 옵션 설정 시 값이 보존되는지 검증한다."""
    relation = OneToMany(
        back_populates="order",
        lazy="selectin",
        cascade="save-update, merge",
        order_by="created_at",
    )
    assert relation.back_populates == "order"
    assert relation.lazy == "selectin"
    assert relation.cascade == "save-update, merge"
    assert relation.order_by == "created_at"


def test_abstract_relationship_is_abstract_metadata() -> None:
    """AbstractRelationship이 AbstractMetadata의 서브클래스인지 검증한다."""
    from spakky.core.common.metadata import AbstractMetadata

    assert issubclass(AbstractRelationship, AbstractMetadata)


def test_extract_one_to_many_list_expect_relation_info() -> None:
    """list[Entity] 타입의 OneToMany 관계가 올바르게 추출되는지 검증한다."""

    @Table(table_name="order_items")
    @dataclass
    class OrderItem:
        id: Annotated[UUID, Uuid(), PrimaryKey()]

    @Table(table_name="orders")
    @dataclass
    class Order:
        id: Annotated[UUID, Uuid(), PrimaryKey()]
        items: Annotated[list[OrderItem], OneToMany(back_populates="order")]

    extractor = Extractor()
    result = extractor.extract(Order)

    assert len(result.relations) == 1
    rel = result.relations[0]
    assert rel.name == "items"
    assert rel.target_entity is OrderItem
    assert rel.collection_class is list
    assert rel.nullable is False
    assert isinstance(rel.relationship_metadata, OneToMany)
    assert rel.relationship_metadata.back_populates == "order"


def test_extract_one_to_many_set_expect_relation_info() -> None:
    """set[Entity] 타입의 OneToMany 관계가 올바르게 추출되는지 검증한다."""

    @Table(table_name="tags")
    @dataclass
    class Tag:
        id: Annotated[UUID, Uuid(), PrimaryKey()]

    @Table(table_name="posts")
    @dataclass
    class Post:
        id: Annotated[UUID, Uuid(), PrimaryKey()]
        tags: Annotated[set[Tag], OneToMany()]

    extractor = Extractor()
    result = extractor.extract(Post)

    assert len(result.relations) == 1
    rel = result.relations[0]
    assert rel.collection_class is set


def test_extract_one_to_many_frozenset_expect_relation_info() -> None:
    """frozenset[Entity] 타입의 OneToMany 관계가 올바르게 추출되는지 검증한다."""

    @Table(table_name="items")
    @dataclass
    class Item:
        id: Annotated[UUID, Uuid(), PrimaryKey()]

    @Table(table_name="containers")
    @dataclass
    class Container:
        id: Annotated[UUID, Uuid(), PrimaryKey()]
        items: Annotated[frozenset[Item], OneToMany()]

    extractor = Extractor()
    result = extractor.extract(Container)

    assert len(result.relations) == 1
    rel = result.relations[0]
    assert rel.collection_class is frozenset


def test_extract_many_to_one_required_expect_relation_info() -> None:
    """필수 ManyToOne 관계가 올바르게 추출되는지 검증한다."""

    @Table(table_name="orders")
    @dataclass
    class Order:
        id: Annotated[UUID, Uuid(), PrimaryKey()]

    @Table(table_name="order_items")
    @dataclass
    class OrderItem:
        id: Annotated[UUID, Uuid(), PrimaryKey()]
        order: Annotated[Order, ManyToOne(back_populates="items")]

    extractor = Extractor()
    result = extractor.extract(OrderItem)

    assert len(result.relations) == 1
    rel = result.relations[0]
    assert rel.name == "order"
    assert rel.target_entity is Order
    assert rel.collection_class is None
    assert rel.nullable is False
    assert isinstance(rel.relationship_metadata, ManyToOne)
    assert rel.relationship_metadata.back_populates == "items"


def test_extract_many_to_one_optional_expect_nullable_true() -> None:
    """Optional ManyToOne 관계가 nullable=True로 추출되는지 검증한다."""

    @Table(table_name="categories")
    @dataclass
    class Category:
        id: Annotated[UUID, Uuid(), PrimaryKey()]

    @Table(table_name="products")
    @dataclass
    class Product:
        id: Annotated[UUID, Uuid(), PrimaryKey()]
        category: Annotated[Category | None, ManyToOne()]

    extractor = Extractor()
    result = extractor.extract(Product)

    assert len(result.relations) == 1
    rel = result.relations[0]
    assert rel.nullable is True
    assert rel.target_entity is Category


def test_extract_relation_not_in_columns_expect_excluded() -> None:
    """관계 필드가 columns에서 제외되는지 검증한다."""

    @Table(table_name="children")
    @dataclass
    class Child:
        id: Annotated[UUID, Uuid(), PrimaryKey()]

    @Table(table_name="parents")
    @dataclass
    class Parent:
        id: Annotated[UUID, Uuid(), PrimaryKey()]
        children: Annotated[list[Child], OneToMany()]

    extractor = Extractor()
    result = extractor.extract(Parent)

    assert "id" in result.columns
    assert "children" not in result.columns
    assert len(result.relations) == 1


def test_extract_mixed_columns_and_relations_expect_separated() -> None:
    """일반 컬럼과 관계 필드가 올바르게 분리되는지 검증한다."""

    @Table(table_name="comments")
    @dataclass
    class Comment:
        id: Annotated[UUID, Uuid(), PrimaryKey()]

    @Table(table_name="articles")
    @dataclass
    class Article:
        id: Annotated[UUID, Uuid(), PrimaryKey()]
        title: str
        content: str
        comments: Annotated[list[Comment], OneToMany()]

    extractor = Extractor()
    result = extractor.extract(Article)

    assert "id" in result.columns
    assert "title" in result.columns
    assert "content" in result.columns
    assert "comments" not in result.columns
    assert len(result.relations) == 1
    assert result.relations[0].name == "comments"


def test_extract_bidirectional_relation_expect_both_extracted() -> None:
    """양방향 관계의 두 엔티티에서 각각 관계가 추출되는지 검증한다."""

    @Table(table_name="authors")
    @dataclass
    class Author:
        id: Annotated[UUID, Uuid(), PrimaryKey()]

    @Table(table_name="books")
    @dataclass
    class Book:
        id: Annotated[UUID, Uuid(), PrimaryKey()]
        author: Annotated[Author, ManyToOne(back_populates="books")]

    # Author에 books 관계를 추가하기 위해 새로 정의
    @Table(table_name="authors_with_books")
    @dataclass
    class AuthorWithBooks:
        id: Annotated[UUID, Uuid(), PrimaryKey()]
        books: Annotated[list[Book], OneToMany(back_populates="author")]

    extractor = Extractor()

    book_result = extractor.extract(Book)
    assert len(book_result.relations) == 1
    assert book_result.relations[0].relationship_metadata.back_populates == "books"

    author_result = extractor.extract(AuthorWithBooks)
    assert len(author_result.relations) == 1
    assert author_result.relations[0].relationship_metadata.back_populates == "author"


def test_one_to_one_relation_type_expect_one_to_one() -> None:
    """OneToOne의 relation_type이 ONE_TO_ONE을 반환하는지 검증한다."""
    relation = OneToOne()
    assert relation.relation_type == RelationType.ONE_TO_ONE


def test_one_to_one_default_values_expect_correct_defaults() -> None:
    """OneToOne의 기본값이 올바르게 설정되는지 검증한다."""
    relation = OneToOne()
    assert relation.back_populates is None
    assert relation.lazy == "select"


def test_one_to_one_with_back_populates_expect_value_preserved() -> None:
    """OneToOne에 back_populates 설정 시 값이 보존되는지 검증한다."""
    relation = OneToOne(back_populates="user")
    assert relation.back_populates == "user"


def test_extract_one_to_one_expect_relation_info() -> None:
    """OneToOne 관계가 올바르게 추출되는지 검증한다."""

    @Table(table_name="profiles")
    @dataclass
    class Profile:
        id: Annotated[UUID, Uuid(), PrimaryKey()]

    @Table(table_name="users")
    @dataclass
    class User:
        id: Annotated[UUID, Uuid(), PrimaryKey()]
        profile: Annotated[Profile, OneToOne(back_populates="user")]

    extractor = Extractor()
    result = extractor.extract(User)

    assert len(result.relations) == 1
    rel = result.relations[0]
    assert rel.name == "profile"
    assert rel.target_entity is Profile
    assert rel.collection_class is None  # OneToOne은 uselist=False
    assert rel.nullable is False
    assert isinstance(rel.relationship_metadata, OneToOne)
    assert rel.relationship_metadata.back_populates == "user"


def test_extract_one_to_one_nullable_expect_nullable_true() -> None:
    """Optional OneToOne 관계가 nullable=True로 추출되는지 검증한다."""

    @Table(table_name="parking_spots")
    @dataclass
    class ParkingSpot:
        id: Annotated[UUID, Uuid(), PrimaryKey()]

    @Table(table_name="employees")
    @dataclass
    class Employee:
        id: Annotated[UUID, Uuid(), PrimaryKey()]
        parking_spot: Annotated[ParkingSpot | None, OneToOne(back_populates="employee")]

    extractor = Extractor()
    result = extractor.extract(Employee)

    assert len(result.relations) == 1
    rel = result.relations[0]
    assert rel.name == "parking_spot"
    assert rel.target_entity is ParkingSpot
    assert rel.collection_class is None
    assert rel.nullable is True
    assert isinstance(rel.relationship_metadata, OneToOne)


def test_extract_bidirectional_one_to_one_expect_both_extracted() -> None:
    """양방향 OneToOne 관계의 두 엔티티에서 각각 관계가 추출되는지 검증한다."""

    @Table(table_name="passports")
    @dataclass
    class Passport:
        id: Annotated[UUID, Uuid(), PrimaryKey()]

    @Table(table_name="citizens")
    @dataclass
    class Citizen:
        id: Annotated[UUID, Uuid(), PrimaryKey()]
        passport: Annotated[Passport, OneToOne(back_populates="citizen")]

    @Table(table_name="passports_with_citizen")
    @dataclass
    class PassportWithCitizen:
        id: Annotated[UUID, Uuid(), PrimaryKey()]
        citizen: Annotated[Citizen, OneToOne(back_populates="passport")]

    extractor = Extractor()

    citizen_result = extractor.extract(Citizen)
    assert len(citizen_result.relations) == 1
    assert citizen_result.relations[0].relationship_metadata.back_populates == "citizen"

    passport_result = extractor.extract(PassportWithCitizen)
    assert len(passport_result.relations) == 1
    assert (
        passport_result.relations[0].relationship_metadata.back_populates == "passport"
    )
