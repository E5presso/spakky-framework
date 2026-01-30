"""Test metadata extraction utilities for Annotated types."""

from dataclasses import dataclass
from typing import Annotated, cast

import pytest

from spakky.core.common.metadata import (
    AbstractMetadata,
    AnnotatedType,
    InvalidAnnotatedTypeError,
    MetadataNotFoundError,
)


@dataclass
class SampleMetadata(AbstractMetadata):
    """Sample metadata for testing purposes."""

    name: str
    value: int = 0


@dataclass
class AnotherMetadata(AbstractMetadata):
    """Another sample metadata for testing purposes."""

    description: str


def test_metadata_not_found_error_has_correct_message() -> None:
    """Test that MetadataNotFoundError has the correct error message."""
    error = MetadataNotFoundError()
    assert error.message == "Expected metadata not found in Annotated type."


def test_invalid_annotated_type_error_has_correct_message() -> None:
    """Test that InvalidAnnotatedTypeError has the correct error message."""
    error = InvalidAnnotatedTypeError()
    assert error.message == "Provided type is not a valid Annotated type."


def test_get_actual_type_with_valid_annotated_type_expect_success() -> None:
    """Test get_actual_type extracts the correct actual type."""
    annotated_type = Annotated[str, SampleMetadata(name="test")]
    actual_type = AbstractMetadata.get_actual_type(cast(AnnotatedType, annotated_type))
    assert actual_type is str


def test_get_actual_type_with_complex_type_expect_success() -> None:
    """Test get_actual_type works with complex types like list[int]."""
    annotated_type = Annotated[list[int], SampleMetadata(name="numbers")]
    actual_type = AbstractMetadata.get_actual_type(cast(AnnotatedType, annotated_type))
    assert actual_type == list[int]


def test_get_actual_type_with_non_annotated_type_expect_error() -> None:
    """Test get_actual_type raises error for non-Annotated type."""
    with pytest.raises(InvalidAnnotatedTypeError):
        AbstractMetadata.get_actual_type(cast(AnnotatedType, str))


def test_all_with_single_metadata_expect_list_with_one_item() -> None:
    """Test all() returns a list with single matching metadata."""
    metadata = SampleMetadata(name="test", value=42)
    annotated_type = Annotated[str, metadata]
    result = SampleMetadata.all(cast(AnnotatedType, annotated_type))
    assert result == [metadata]


def test_all_with_multiple_same_metadata_expect_list_with_all_items() -> None:
    """Test all() returns all matching metadata instances."""
    metadata1 = SampleMetadata(name="first", value=1)
    metadata2 = SampleMetadata(name="second", value=2)
    annotated_type = Annotated[str, metadata1, metadata2]
    result = SampleMetadata.all(cast(AnnotatedType, annotated_type))
    assert result == [metadata1, metadata2]


def test_all_with_no_matching_metadata_expect_empty_list() -> None:
    """Test all() returns empty list when no matching metadata exists."""
    annotated_type = Annotated[str, AnotherMetadata(description="other")]
    result = SampleMetadata.all(cast(AnnotatedType, annotated_type))
    assert result == []


def test_all_with_mixed_metadata_expect_only_matching_items() -> None:
    """Test all() returns only matching metadata, ignoring other types."""
    sample = SampleMetadata(name="sample", value=10)
    another = AnotherMetadata(description="another")
    annotated_type = Annotated[str, sample, another]
    result = SampleMetadata.all(cast(AnnotatedType, annotated_type))
    assert result == [sample]


def test_all_with_non_annotated_type_expect_empty_list() -> None:
    """Test all() returns empty list for non-Annotated type."""
    result = SampleMetadata.all(cast(AnnotatedType, str))
    assert result == []


def test_get_with_existing_metadata_expect_success() -> None:
    """Test get() returns the metadata instance when it exists."""
    metadata = SampleMetadata(name="test", value=99)
    annotated_type = Annotated[str, metadata]
    result = SampleMetadata.get(cast(AnnotatedType, annotated_type))
    assert result == metadata


def test_get_with_no_matching_metadata_expect_error() -> None:
    """Test get() raises MetadataNotFoundError when metadata doesn't exist."""
    annotated_type = Annotated[str, AnotherMetadata(description="other")]
    with pytest.raises(MetadataNotFoundError):
        SampleMetadata.get(cast(AnnotatedType, annotated_type))


def test_get_with_multiple_metadata_expect_first_match() -> None:
    """Test get() returns the first matching metadata when multiple exist."""
    metadata1 = SampleMetadata(name="first", value=1)
    metadata2 = SampleMetadata(name="second", value=2)
    annotated_type = Annotated[str, metadata1, metadata2]
    result = SampleMetadata.get(cast(AnnotatedType, annotated_type))
    assert result == metadata1


def test_get_with_non_annotated_type_expect_error() -> None:
    """Test get() raises InvalidAnnotatedTypeError for non-Annotated type."""
    with pytest.raises(InvalidAnnotatedTypeError):
        SampleMetadata.get(cast(AnnotatedType, str))


def test_get_or_none_with_existing_metadata_expect_success() -> None:
    """Test get_or_none() returns metadata when it exists."""
    metadata = SampleMetadata(name="test", value=50)
    annotated_type = Annotated[str, metadata]
    result = SampleMetadata.get_or_none(cast(AnnotatedType, annotated_type))
    assert result == metadata


def test_get_or_none_with_no_matching_metadata_expect_none() -> None:
    """Test get_or_none() returns None when metadata doesn't exist."""
    annotated_type = Annotated[str, AnotherMetadata(description="other")]
    result = SampleMetadata.get_or_none(cast(AnnotatedType, annotated_type))
    assert result is None


def test_get_or_none_with_multiple_metadata_expect_first_match() -> None:
    """Test get_or_none() returns the first matching metadata when multiple exist."""
    metadata1 = SampleMetadata(name="first", value=1)
    metadata2 = SampleMetadata(name="second", value=2)
    annotated_type = Annotated[str, metadata1, metadata2]
    result = SampleMetadata.get_or_none(cast(AnnotatedType, annotated_type))
    assert result == metadata1


def test_get_or_none_with_non_annotated_type_expect_none() -> None:
    """Test get_or_none() returns None for non-Annotated type."""
    result = SampleMetadata.get_or_none(cast(AnnotatedType, str))
    assert result is None


def test_get_or_default_with_existing_metadata_expect_success() -> None:
    """Test get_or_default() returns metadata when it exists."""
    metadata = SampleMetadata(name="test", value=77)
    default = SampleMetadata(name="default", value=0)
    annotated_type = Annotated[str, metadata]
    result = SampleMetadata.get_or_default(cast(AnnotatedType, annotated_type), default)
    assert result == metadata


def test_get_or_default_with_no_matching_metadata_expect_default() -> None:
    """Test get_or_default() returns default when metadata doesn't exist."""
    default = SampleMetadata(name="default", value=999)
    annotated_type = Annotated[str, AnotherMetadata(description="other")]
    result = SampleMetadata.get_or_default(cast(AnnotatedType, annotated_type), default)
    assert result == default


def test_get_or_default_with_multiple_metadata_expect_first_match() -> None:
    """Test get_or_default() returns first matching metadata when multiple exist."""
    metadata1 = SampleMetadata(name="first", value=1)
    metadata2 = SampleMetadata(name="second", value=2)
    default = SampleMetadata(name="default", value=0)
    annotated_type = Annotated[str, metadata1, metadata2]
    result = SampleMetadata.get_or_default(cast(AnnotatedType, annotated_type), default)
    assert result == metadata1


def test_get_or_default_with_non_annotated_type_expect_default() -> None:
    """Test get_or_default() returns default for non-Annotated type."""
    default = SampleMetadata(name="default", value=0)
    result = SampleMetadata.get_or_default(cast(AnnotatedType, str), default)
    assert result == default


def test_exists_with_matching_metadata_expect_true() -> None:
    """Test exists() returns True when metadata exists."""
    annotated_type = Annotated[str, SampleMetadata(name="test")]
    result = SampleMetadata.exists(cast(AnnotatedType, annotated_type))
    assert result is True


def test_exists_with_no_matching_metadata_expect_false() -> None:
    """Test exists() returns False when metadata doesn't exist."""
    annotated_type = Annotated[str, AnotherMetadata(description="other")]
    result = SampleMetadata.exists(cast(AnnotatedType, annotated_type))
    assert result is False


def test_exists_with_multiple_metadata_types_expect_true_for_matching() -> None:
    """Test exists() returns True even with mixed metadata types."""
    annotated_type = Annotated[
        str,
        AnotherMetadata(description="first"),
        SampleMetadata(name="second"),
    ]
    assert SampleMetadata.exists(cast(AnnotatedType, annotated_type)) is True
    assert AnotherMetadata.exists(cast(AnnotatedType, annotated_type)) is True


def test_exists_with_empty_metadata_expect_false() -> None:
    """Test exists() returns False when no metadata is present."""
    annotated_type = Annotated[str, "not_a_metadata"]
    result = SampleMetadata.exists(cast(AnnotatedType, annotated_type))
    assert result is False


def test_exists_with_non_annotated_type_expect_false() -> None:
    """Test exists() returns False for non-Annotated type."""
    result = SampleMetadata.exists(cast(AnnotatedType, str))
    assert result is False


def test_all_with_non_metadata_values_expect_only_metadata_instances() -> None:
    """Test all() filters out non-metadata values in Annotated type."""
    metadata = SampleMetadata(name="valid", value=123)
    annotated_type = Annotated[str, "string_value", metadata, 42]
    result = SampleMetadata.all(cast(AnnotatedType, annotated_type))
    assert result == [metadata]
