"""Unit tests for ORM Table annotation."""

from uuid import UUID, uuid4

import pytest
from spakky.core.common.annotation import AnnotationNotFoundError
from spakky.core.common.mutability import mutable
from spakky.domain.models.entity import AbstractEntity

from spakky.plugins.sqlalchemy.orm import Table


def test_table_annotation_with_custom_name() -> None:
    """Test that @Table annotation with custom name works correctly."""

    @mutable
    @Table(name="custom_products")
    class Product(AbstractEntity[UUID]):
        name: str
        price: int

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        def validate(self) -> None:
            pass

    table = Table.get(Product)
    assert table.name == "custom_products"


def test_table_annotation_not_found() -> None:
    """Test that Table.get raises AnnotationNotFoundError when not annotated."""

    @mutable
    class NotAnnotated(AbstractEntity[UUID]):
        name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        def validate(self) -> None:
            pass

    with pytest.raises(AnnotationNotFoundError):
        Table.get(NotAnnotated)


def test_table_annotation_or_none() -> None:
    """Test that Table.get_or_none returns None when not annotated."""

    @mutable
    class NotAnnotated(AbstractEntity[UUID]):
        name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        def validate(self) -> None:
            pass

    assert Table.get_or_none(NotAnnotated) is None


def test_table_annotation_automatically_applies_mutable() -> None:
    """Test that @Table annotation makes the class mutable (dataclass-like)."""

    @mutable
    @Table(name="products")
    class Product(AbstractEntity[UUID]):
        name: str
        price: int

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        def validate(self) -> None:
            pass

    product = Product(uid=Product.next_id(), name="Test", price=100)
    assert product.name == "Test"
    assert product.price == 100


def test_table_annotation_auto_generates_name_from_class() -> None:
    """Test that @Table() without name auto-generates snake_case table name from class name."""

    @mutable
    @Table()
    class OrderItem(AbstractEntity[UUID]):
        quantity: int

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        def validate(self) -> None:
            pass

    table = Table.get(OrderItem)
    assert table.name == "order_item"
