"""Tests for String field metadata."""

from typing import Annotated, cast

from spakky.core.common.metadata import AnnotatedType

from spakky.plugins.sqlalchemy.orm.fields.string import String


def test_string_default_length_expect_255() -> None:
    """String 필드의 기본 length가 255인지 검증한다."""
    field = String()
    assert field.length == 255


def test_string_custom_length_expect_value() -> None:
    """String 필드에 커스텀 length를 설정할 수 있는지 검증한다."""
    field = String(length=100)
    assert field.length == 100


def test_string_get_from_annotated_expect_correct_length() -> None:
    """Annotated 타입에서 String 메타데이터를 추출하고 length가 올바른지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[str, String(length=50)])
    field = String.get(annotated)
    assert field.length == 50


def test_string_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 String이 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[str, String()])
    assert String.exists(annotated) is True


def test_string_with_all_options_expect_correct_values() -> None:
    """String 필드에 모든 옵션을 설정했을 때 값이 올바른지 검증한다."""
    field = String(
        length=128,
        nullable=False,
        default="default_value",
        name="custom_name",
        comment="A string column",
    )
    assert field.length == 128
    assert field.nullable is False
    assert field.default == "default_value"
    assert field.name == "custom_name"
    assert field.comment == "A string column"


def test_string_get_or_none_from_annotated_expect_string() -> None:
    """Annotated 타입에서 String.get_or_none()이 String을 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[str, String(length=200)])
    result = String.get_or_none(annotated)
    assert result is not None
    assert result.length == 200


def test_string_get_or_none_without_string_expect_none() -> None:
    """String 메타데이터가 없는 Annotated 타입에서 get_or_none()이 None을 반환하는지 검증한다."""
    result = String.get_or_none(cast(AnnotatedType, str))
    assert result is None
