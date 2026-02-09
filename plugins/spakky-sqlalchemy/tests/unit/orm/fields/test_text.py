"""Tests for Text field metadata."""

from typing import Annotated, cast

from spakky.core.common.metadata import AnnotatedType

from spakky.plugins.sqlalchemy.orm.fields.text import Text


def test_text_default_collation_expect_none() -> None:
    """Text 필드의 기본 collation이 None인지 검증한다."""
    field = Text()
    assert field.collation is None


def test_text_custom_collation_expect_value() -> None:
    """Text 필드에 커스텀 collation을 설정할 수 있는지 검증한다."""
    field = Text(collation="utf8mb4_unicode_ci")
    assert field.collation == "utf8mb4_unicode_ci"


def test_text_get_from_annotated_expect_text_instance() -> None:
    """Annotated 타입에서 Text 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[str, Text()])
    field = Text.get(annotated)
    assert isinstance(field, Text)


def test_text_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 Text가 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[str, Text()])
    assert Text.exists(annotated) is True


def test_text_with_all_options_expect_correct_values() -> None:
    """Text 필드에 모든 옵션을 설정했을 때 값이 올바른지 검증한다."""
    field = Text(
        collation="utf8_general_ci",
        nullable=False,
        name="description_col",
        comment="Article content",
    )
    assert field.collation == "utf8_general_ci"
    assert field.nullable is False
    assert field.name == "description_col"
    assert field.comment == "Article content"


def test_text_inherits_abstract_field_defaults() -> None:
    """Text 필드가 AbstractField의 기본값을 올바르게 상속하는지 검증한다."""
    field = Text()
    assert field.nullable is True
    assert field.default is None
    assert field.default_factory is None
    assert field.name == ""
    assert field.comment is None
