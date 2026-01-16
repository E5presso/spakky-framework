"""Unit tests for metadata extractor."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated
from uuid import UUID, uuid4

import pytest
from spakky.core.common.annotation import AnnotationNotFoundError
from spakky.core.common.mutability import mutable
from spakky.domain.models.aggregate_root import AbstractAggregateRoot
from spakky.domain.models.entity import AbstractEntity

from spakky.plugins.sqlalchemy.orm import (
    DecimalField,
    EntityMetadata,
    FieldMetadata,
    MetadataExtractor,
    StringField,
    Table,
)


@pytest.fixture
def extractor() -> MetadataExtractor:
    """Create a MetadataExtractor instance for testing."""
    return MetadataExtractor()


@mutable
@Table(name="simple_user")
class SimpleUser(AbstractEntity[UUID]):
    """Simple test entity with basic fields."""

    name: str
    email: str | None

    @classmethod
    def next_id(cls) -> UUID:
        return uuid4()

    def validate(self) -> None:
        pass


@mutable
@Table(name="custom_products")
class Product(AbstractEntity[UUID]):
    """Test entity with custom table name."""

    name: str
    price: int

    @classmethod
    def next_id(cls) -> UUID:
        return uuid4()

    def validate(self) -> None:
        pass


class OrderStatus(Enum):
    """Test enum for order status."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"


@mutable
@Table(name="order")
class Order(AbstractAggregateRoot[UUID]):
    """Test aggregate root with enum field."""

    status: OrderStatus
    total: Decimal

    @classmethod
    def next_id(cls) -> UUID:
        return uuid4()

    def validate(self) -> None:
        pass


@mutable
@Table(name="annotated_entity")
class AnnotatedEntity(AbstractEntity[UUID]):
    """Test entity with Annotated field metadata."""

    email: Annotated[str, StringField(max_length=255, unique=True)]
    price: Annotated[Decimal, DecimalField(precision=10, scale=2)]

    @classmethod
    def next_id(cls) -> UUID:
        return uuid4()

    def validate(self) -> None:
        pass


def test_extract_simple_entity(extractor: MetadataExtractor) -> None:
    """Test extracting metadata from a simple entity."""
    metadata = extractor.extract(SimpleUser)

    assert isinstance(metadata, EntityMetadata)
    assert metadata.entity_class is SimpleUser
    assert metadata.table_name == "simple_user"
    # uid, version, created_at, updated_at, name, email = 6 fields
    assert len(metadata.fields) == 6


def test_extract_entity_primary_key(extractor: MetadataExtractor) -> None:
    """Test that uid is recognized as primary key."""
    metadata = extractor.extract(SimpleUser)

    uid_field = metadata.get_field("uid")
    assert uid_field is not None
    assert uid_field.is_primary_key is True
    assert uid_field.nullable is False

    # Other fields should not be primary key
    name_field = metadata.get_field("name")
    assert name_field is not None
    assert name_field.is_primary_key is False


def test_extract_entity_nullable_field(extractor: MetadataExtractor) -> None:
    """Test that Optional/Union with None fields are detected as nullable."""
    metadata = extractor.extract(SimpleUser)

    email_field = metadata.get_field("email")
    assert email_field is not None
    assert email_field.nullable is True
    assert email_field.python_type is str

    name_field = metadata.get_field("name")
    assert name_field is not None
    assert name_field.nullable is False


def test_extract_entity_common_fields(extractor: MetadataExtractor) -> None:
    """Test that common entity fields are extracted."""
    metadata = extractor.extract(SimpleUser)

    # Check version field
    version_field = metadata.get_field("version")
    assert version_field is not None
    assert version_field.python_type is UUID
    assert version_field.default_factory is not None

    # Check created_at field
    created_at_field = metadata.get_field("created_at")
    assert created_at_field is not None
    assert created_at_field.python_type is datetime
    assert created_at_field.default_factory is not None

    # Check updated_at field
    updated_at_field = metadata.get_field("updated_at")
    assert updated_at_field is not None
    assert updated_at_field.python_type is datetime
    assert updated_at_field.default_factory is not None


def test_extract_entity_with_custom_table_name(extractor: MetadataExtractor) -> None:
    """Test extracting metadata from entity with custom table name."""
    metadata = extractor.extract(Product)

    assert metadata.table_name == "custom_products"


def test_extract_aggregate_root(extractor: MetadataExtractor) -> None:
    """Test extracting metadata from an aggregate root."""
    metadata = extractor.extract(Order)

    assert isinstance(metadata, EntityMetadata)
    assert metadata.entity_class is Order
    assert metadata.table_name == "order"

    # Check enum field
    status_field = metadata.get_field("status")
    assert status_field is not None
    assert status_field.python_type is OrderStatus
    assert status_field.nullable is False


def test_extract_skips_private_fields(extractor: MetadataExtractor) -> None:
    """Test that private fields (starting with _) are skipped."""
    metadata = extractor.extract(Order)

    # __events is a private field in AbstractAggregateRoot
    for field in metadata.fields:
        assert not field.name.startswith("_")


def test_extract_with_annotated_metadata(extractor: MetadataExtractor) -> None:
    """Test extracting field metadata from Annotated types."""
    metadata = extractor.extract(AnnotatedEntity)

    email_field = metadata.get_field("email")
    assert email_field is not None
    assert email_field.field_info is not None
    assert isinstance(email_field.field_info, StringField)
    assert email_field.field_info.max_length == 255
    assert email_field.field_info.unique is True

    price_field = metadata.get_field("price")
    assert price_field is not None
    assert price_field.field_info is not None
    assert isinstance(price_field.field_info, DecimalField)
    assert price_field.field_info.precision == 10
    assert price_field.field_info.scale == 2


def test_extract_primary_key_property(extractor: MetadataExtractor) -> None:
    """Test the primary_key_field property."""
    metadata = extractor.extract(SimpleUser)

    pk_field = metadata.primary_key_field
    assert pk_field is not None
    assert pk_field.name == "uid"
    assert pk_field.is_primary_key is True


def test_extract_get_field_not_found(extractor: MetadataExtractor) -> None:
    """Test get_field returns None for non-existent field."""
    metadata = extractor.extract(SimpleUser)

    assert metadata.get_field("nonexistent") is None


def test_extract_without_table_annotation(extractor: MetadataExtractor) -> None:
    """Test that AnnotationNotFoundError is raised when entity lacks @Table annotation."""

    @mutable
    class NoTableAnnotation(AbstractEntity[UUID]):
        name: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid4()

        def validate(self) -> None:
            pass

    with pytest.raises(AnnotationNotFoundError):
        extractor.extract(NoTableAnnotation)


def test_field_metadata_is_frozen() -> None:
    """Test that FieldMetadata is immutable."""
    field = FieldMetadata(name="test", python_type=str)

    with pytest.raises(AttributeError):
        field.name = "changed"  # type: ignore


def test_entity_metadata_is_frozen(extractor: MetadataExtractor) -> None:
    """Test that EntityMetadata is immutable."""
    metadata = extractor.extract(SimpleUser)

    with pytest.raises(AttributeError):
        metadata.table_name = "changed"  # type: ignore
