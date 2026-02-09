"""Tests for Binary field metadata."""

from typing import Annotated, cast

from spakky.core.common.metadata import AnnotatedType

from spakky.plugins.sqlalchemy.orm.fields.binary import Binary


def test_binary_default_length_expect_none() -> None:
    """Binary 필드의 기본 length가 None인지 검증한다."""
    field = Binary()
    assert field.length is None


def test_binary_custom_length_expect_value() -> None:
    """Binary 필드에 커스텀 length를 설정할 수 있는지 검증한다."""
    field = Binary(length=1024)
    assert field.length == 1024


def test_binary_get_from_annotated_expect_instance() -> None:
    """Annotated 타입에서 Binary 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[bytes, Binary(length=512)])
    field = Binary.get(annotated)
    assert isinstance(field, Binary)
    assert field.length == 512


def test_binary_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 Binary가 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[bytes, Binary()])
    assert Binary.exists(annotated) is True


def test_binary_with_all_options_expect_correct_values() -> None:
    """Binary 필드에 모든 옵션을 설정했을 때 값이 올바른지 검증한다."""
    field = Binary(
        length=2048,
        nullable=False,
        name="file_data",
        comment="Binary file content",
    )
    assert field.length == 2048
    assert field.nullable is False
    assert field.name == "file_data"
    assert field.comment == "Binary file content"


def test_binary_inherits_abstract_field_defaults() -> None:
    """Binary 필드가 AbstractField의 기본값을 올바르게 상속하는지 검증한다."""
    field = Binary()
    assert field.nullable is True
    assert field.default is None
    assert field.default_factory is None
    assert field.name == ""
    assert field.comment is None
