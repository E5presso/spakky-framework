"""Tests for Boolean field metadata."""

from typing import Annotated, cast

from spakky.core.common.metadata import AnnotatedType

from spakky.plugins.sqlalchemy.orm.fields.boolean import Boolean


def test_boolean_default_values_expect_abstract_field_defaults() -> None:
    """Boolean 필드가 AbstractField 기본값을 올바르게 상속하는지 검증한다."""
    field = Boolean()
    assert field.nullable is True
    assert field.default is None
    assert field.default_factory is None
    assert field.name == ""
    assert field.comment is None


def test_boolean_get_from_annotated_expect_instance() -> None:
    """Annotated 타입에서 Boolean 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[bool, Boolean()])
    field = Boolean.get(annotated)
    assert isinstance(field, Boolean)


def test_boolean_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 Boolean이 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[bool, Boolean()])
    assert Boolean.exists(annotated) is True


def test_boolean_with_options_expect_correct_values() -> None:
    """Boolean 필드에 옵션을 설정했을 때 값이 올바른지 검증한다."""
    field = Boolean(
        nullable=False,
        default=False,
        name="is_active",
        comment="Whether the user is active",
    )
    assert field.nullable is False
    assert field.default is False
    assert field.name == "is_active"
    assert field.comment == "Whether the user is active"


def test_boolean_get_or_none_from_annotated_expect_boolean() -> None:
    """Annotated 타입에서 Boolean.get_or_none()이 Boolean을 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[bool, Boolean(nullable=False)])
    result = Boolean.get_or_none(annotated)
    assert result is not None
    assert result.nullable is False
