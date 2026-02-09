"""Tests for JSON field metadata."""

from typing import Annotated, Any, cast

from spakky.core.common.metadata import AnnotatedType

from spakky.plugins.sqlalchemy.orm.fields.json import JSON


def test_json_default_values_expect_abstract_field_defaults() -> None:
    """JSON 필드가 AbstractField 기본값을 올바르게 상속하는지 검증한다."""
    field = JSON()
    assert field.nullable is True
    assert field.default is None
    assert field.default_factory is None
    assert field.name == ""
    assert field.comment is None


def test_json_get_from_annotated_expect_instance() -> None:
    """Annotated 타입에서 JSON 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[dict[str, Any], JSON()])
    field = JSON.get(annotated)
    assert isinstance(field, JSON)


def test_json_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 JSON이 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[dict[str, Any], JSON()])
    assert JSON.exists(annotated) is True


def test_json_with_options_expect_correct_values() -> None:
    """JSON 필드에 옵션을 설정했을 때 값이 올바른지 검증한다."""
    field = JSON(
        nullable=False,
        name="settings",
        comment="User settings JSON",
    )
    assert field.nullable is False
    assert field.name == "settings"
    assert field.comment == "User settings JSON"


def test_json_with_default_factory_expect_callable() -> None:
    """JSON 필드에 default_factory를 설정할 수 있는지 검증한다."""
    field = JSON(default_factory=dict)
    assert field.default_factory is dict
    assert field.default_factory() == {}
