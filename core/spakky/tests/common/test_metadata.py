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
    """MetadataNotFoundError가 올바른 오류 메시지를 가지고 있음을 검증한다."""
    error = MetadataNotFoundError()
    assert error.message == "Expected metadata not found in Annotated type."


def test_invalid_annotated_type_error_has_correct_message() -> None:
    """InvalidAnnotatedTypeError가 올바른 오류 메시지를 가지고 있음을 검증한다."""
    error = InvalidAnnotatedTypeError()
    assert error.message == "Provided type is not a valid Annotated type."


def test_get_actual_type_with_valid_annotated_type_expect_success() -> None:
    """get_actual_type이 Annotated 타입에서 실제 타입을 올바르게 추출함을 검증한다."""
    annotated_type = Annotated[str, SampleMetadata(name="test")]
    actual_type = AbstractMetadata.get_actual_type(cast(AnnotatedType, annotated_type))
    assert actual_type is str


def test_get_actual_type_with_complex_type_expect_success() -> None:
    """get_actual_type이 list[int] 같은 복잡한 타입에서도 정상 동작함을 검증한다."""
    annotated_type = Annotated[list[int], SampleMetadata(name="numbers")]
    actual_type = AbstractMetadata.get_actual_type(cast(AnnotatedType, annotated_type))
    assert actual_type == list[int]


def test_get_actual_type_with_non_annotated_type_expect_error() -> None:
    """Annotated가 아닌 타입에 대해 get_actual_type이 오류를 발생시킴을 검증한다."""
    with pytest.raises(InvalidAnnotatedTypeError):
        AbstractMetadata.get_actual_type(cast(AnnotatedType, str))


def test_all_with_single_metadata_expect_list_with_one_item() -> None:
    """all()이 단일 메타데이터가 있을 때 하나의 항목을 포함한 리스트를 반환함을 검증한다."""
    metadata = SampleMetadata(name="test", value=42)
    annotated_type = Annotated[str, metadata]
    result = SampleMetadata.all(cast(AnnotatedType, annotated_type))
    assert result == [metadata]


def test_all_with_multiple_same_metadata_expect_list_with_all_items() -> None:
    """all()이 여러 개의 동일한 메타데이터를 모두 반환함을 검증한다."""
    metadata1 = SampleMetadata(name="first", value=1)
    metadata2 = SampleMetadata(name="second", value=2)
    annotated_type = Annotated[str, metadata1, metadata2]
    result = SampleMetadata.all(cast(AnnotatedType, annotated_type))
    assert result == [metadata1, metadata2]


def test_all_with_no_matching_metadata_expect_empty_list() -> None:
    """일치하는 메타데이터가 없을 때 all()이 빈 리스트를 반환함을 검증한다."""
    annotated_type = Annotated[str, AnotherMetadata(description="other")]
    result = SampleMetadata.all(cast(AnnotatedType, annotated_type))
    assert result == []


def test_all_with_mixed_metadata_expect_only_matching_items() -> None:
    """혼합된 메타데이터 중 일치하는 항목만 all()이 반환함을 검증한다."""
    sample = SampleMetadata(name="sample", value=10)
    another = AnotherMetadata(description="another")
    annotated_type = Annotated[str, sample, another]
    result = SampleMetadata.all(cast(AnnotatedType, annotated_type))
    assert result == [sample]


def test_all_with_non_annotated_type_expect_empty_list() -> None:
    """Annotated가 아닌 타입에 대해 all()이 빈 리스트를 반환함을 검증한다."""
    result = SampleMetadata.all(cast(AnnotatedType, str))
    assert result == []


def test_get_with_existing_metadata_expect_success() -> None:
    """메타데이터가 존재할 때 get()이 해당 인스턴스를 반환함을 검증한다."""
    metadata = SampleMetadata(name="test", value=99)
    annotated_type = Annotated[str, metadata]
    result = SampleMetadata.get(cast(AnnotatedType, annotated_type))
    assert result == metadata


def test_get_with_no_matching_metadata_expect_error() -> None:
    """메타데이터가 없을 때 get()이 MetadataNotFoundError를 발생시킴을 검증한다."""
    annotated_type = Annotated[str, AnotherMetadata(description="other")]
    with pytest.raises(MetadataNotFoundError):
        SampleMetadata.get(cast(AnnotatedType, annotated_type))


def test_get_with_multiple_metadata_expect_first_match() -> None:
    """여러 메타데이터가 있을 때 get()이 첫 번째 일치 항목을 반환함을 검증한다."""
    metadata1 = SampleMetadata(name="first", value=1)
    metadata2 = SampleMetadata(name="second", value=2)
    annotated_type = Annotated[str, metadata1, metadata2]
    result = SampleMetadata.get(cast(AnnotatedType, annotated_type))
    assert result == metadata1


def test_get_with_non_annotated_type_expect_error() -> None:
    """Annotated가 아닌 타입에 대해 get()이 InvalidAnnotatedTypeError를 발생시킴을 검증한다."""
    with pytest.raises(InvalidAnnotatedTypeError):
        SampleMetadata.get(cast(AnnotatedType, str))


def test_get_or_none_with_existing_metadata_expect_success() -> None:
    """메타데이터가 존재할 때 get_or_none()이 해당 인스턴스를 반환함을 검증한다."""
    metadata = SampleMetadata(name="test", value=50)
    annotated_type = Annotated[str, metadata]
    result = SampleMetadata.get_or_none(cast(AnnotatedType, annotated_type))
    assert result == metadata


def test_get_or_none_with_no_matching_metadata_expect_none() -> None:
    """메타데이터가 없을 때 get_or_none()이 None을 반환함을 검증한다."""
    annotated_type = Annotated[str, AnotherMetadata(description="other")]
    result = SampleMetadata.get_or_none(cast(AnnotatedType, annotated_type))
    assert result is None


def test_get_or_none_with_multiple_metadata_expect_first_match() -> None:
    """여러 메타데이터가 있을 때 get_or_none()이 첫 번째 일치 항목을 반환함을 검증한다."""
    metadata1 = SampleMetadata(name="first", value=1)
    metadata2 = SampleMetadata(name="second", value=2)
    annotated_type = Annotated[str, metadata1, metadata2]
    result = SampleMetadata.get_or_none(cast(AnnotatedType, annotated_type))
    assert result == metadata1


def test_get_or_none_with_non_annotated_type_expect_none() -> None:
    """Annotated가 아닌 타입에 대해 get_or_none()이 None을 반환함을 검증한다."""
    result = SampleMetadata.get_or_none(cast(AnnotatedType, str))
    assert result is None


def test_get_or_default_with_existing_metadata_expect_success() -> None:
    """메타데이터가 존재할 때 get_or_default()가 해당 인스턴스를 반환함을 검증한다."""
    metadata = SampleMetadata(name="test", value=77)
    default = SampleMetadata(name="default", value=0)
    annotated_type = Annotated[str, metadata]
    result = SampleMetadata.get_or_default(cast(AnnotatedType, annotated_type), default)
    assert result == metadata


def test_get_or_default_with_no_matching_metadata_expect_default() -> None:
    """메타데이터가 없을 때 get_or_default()가 기본값을 반환함을 검증한다."""
    default = SampleMetadata(name="default", value=999)
    annotated_type = Annotated[str, AnotherMetadata(description="other")]
    result = SampleMetadata.get_or_default(cast(AnnotatedType, annotated_type), default)
    assert result == default


def test_get_or_default_with_multiple_metadata_expect_first_match() -> None:
    """여러 메타데이터가 있을 때 get_or_default()가 첫 번째 일치 항목을 반환함을 검증한다."""
    metadata1 = SampleMetadata(name="first", value=1)
    metadata2 = SampleMetadata(name="second", value=2)
    default = SampleMetadata(name="default", value=0)
    annotated_type = Annotated[str, metadata1, metadata2]
    result = SampleMetadata.get_or_default(cast(AnnotatedType, annotated_type), default)
    assert result == metadata1


def test_get_or_default_with_non_annotated_type_expect_default() -> None:
    """Annotated가 아닌 타입에 대해 get_or_default()가 기본값을 반환함을 검증한다."""
    default = SampleMetadata(name="default", value=0)
    result = SampleMetadata.get_or_default(cast(AnnotatedType, str), default)
    assert result == default


def test_exists_with_matching_metadata_expect_true() -> None:
    """메타데이터가 존재할 때 exists()가 True를 반환함을 검증한다."""
    annotated_type = Annotated[str, SampleMetadata(name="test")]
    result = SampleMetadata.exists(cast(AnnotatedType, annotated_type))
    assert result is True


def test_exists_with_no_matching_metadata_expect_false() -> None:
    """메타데이터가 없을 때 exists()가 False를 반환함을 검증한다."""
    annotated_type = Annotated[str, AnotherMetadata(description="other")]
    result = SampleMetadata.exists(cast(AnnotatedType, annotated_type))
    assert result is False


def test_exists_with_multiple_metadata_types_expect_true_for_matching() -> None:
    """혼합된 메타데이터 타입이 있을 때 일치하는 타입에 대해 exists()가 True를 반환함을 검증한다."""
    annotated_type = Annotated[
        str,
        AnotherMetadata(description="first"),
        SampleMetadata(name="second"),
    ]
    assert SampleMetadata.exists(cast(AnnotatedType, annotated_type)) is True
    assert AnotherMetadata.exists(cast(AnnotatedType, annotated_type)) is True


def test_exists_with_empty_metadata_expect_false() -> None:
    """메타데이터가 없을 때 exists()가 False를 반환함을 검증한다."""
    annotated_type = Annotated[str, "not_a_metadata"]
    result = SampleMetadata.exists(cast(AnnotatedType, annotated_type))
    assert result is False


def test_exists_with_non_annotated_type_expect_false() -> None:
    """Annotated가 아닌 타입에 대해 exists()가 False를 반환함을 검증한다."""
    result = SampleMetadata.exists(cast(AnnotatedType, str))
    assert result is False


def test_all_with_non_metadata_values_expect_only_metadata_instances() -> None:
    """Annotated 타입에서 메타데이터가 아닌 값을 all()이 필터링함을 검증한다."""
    metadata = SampleMetadata(name="valid", value=123)
    annotated_type = Annotated[str, "string_value", metadata, 42]
    result = SampleMetadata.all(cast(AnnotatedType, annotated_type))
    assert result == [metadata]
