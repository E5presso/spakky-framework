"""Tests for AbstractField base class."""

from typing import Annotated, cast
from unittest.mock import MagicMock

from spakky.core.common.metadata import AnnotatedType

from spakky.plugins.sqlalchemy.orm.fields.base import AbstractField
from spakky.plugins.sqlalchemy.orm.fields.string import String


def test_abstract_field_default_nullable_expect_true() -> None:
    """AbstractField의 기본 nullable 값이 True인지 검증한다."""
    field = String()
    assert field.nullable is True


def test_abstract_field_nullable_false_expect_false() -> None:
    """AbstractField의 nullable을 False로 설정할 수 있는지 검증한다."""
    field = String(nullable=False)
    assert field.nullable is False


def test_abstract_field_default_value_expect_none() -> None:
    """AbstractField의 기본 default 값이 None인지 검증한다."""
    field = String()
    assert field.default is None


def test_abstract_field_custom_default_expect_value() -> None:
    """AbstractField에 커스텀 default 값을 설정할 수 있는지 검증한다."""
    field = String(default="hello")
    assert field.default == "hello"


def test_abstract_field_default_factory_expect_none() -> None:
    """AbstractField의 기본 default_factory 값이 None인지 검증한다."""
    field = String()
    assert field.default_factory is None


def test_abstract_field_custom_default_factory_expect_callable() -> None:
    """AbstractField에 default_factory를 설정할 수 있는지 검증한다."""
    factory = MagicMock(return_value="generated")
    field = String(default_factory=factory)
    assert field.default_factory is not None
    assert field.default_factory is factory
    assert field.default_factory() == "generated"


def test_abstract_field_default_name_expect_empty() -> None:
    """AbstractField의 기본 name 값이 빈 문자열인지 검증한다."""
    field = String()
    assert field.name == ""


def test_abstract_field_custom_name_expect_value() -> None:
    """AbstractField에 커스텀 name을 설정할 수 있는지 검증한다."""
    field = String(name="custom_col")
    assert field.name == "custom_col"


def test_abstract_field_default_comment_expect_none() -> None:
    """AbstractField의 기본 comment 값이 None인지 검증한다."""
    field = String()
    assert field.comment is None


def test_abstract_field_custom_comment_expect_value() -> None:
    """AbstractField에 커스텀 comment를 설정할 수 있는지 검증한다."""
    field = String(comment="User email address")
    assert field.comment == "User email address"


def test_abstract_field_get_from_annotated_expect_field_instance() -> None:
    """Annotated 타입에서 AbstractField.get()으로 필드 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[str, String(length=100)])
    field = AbstractField.get(annotated)
    assert isinstance(field, String)


def test_abstract_field_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 AbstractField가 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[str, String(length=50)])
    assert AbstractField.exists(annotated) is True


def test_abstract_field_exists_in_plain_type_expect_false() -> None:
    """일반 타입에서 AbstractField.exists()가 False를 반환하는지 검증한다."""
    assert AbstractField.exists(cast(AnnotatedType, str)) is False


def test_abstract_field_mutability_expect_mutable() -> None:
    """AbstractField 서브클래스 인스턴스가 mutable인지 검증한다."""
    field = String(length=100)
    field.nullable = False
    assert not field.nullable
    field.name = "updated"
    assert field.name == "updated"


def test_abstract_field_all_from_annotated_expect_list() -> None:
    """Annotated 타입에서 AbstractField.all()으로 모든 필드 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[str, String(length=100)])
    fields = AbstractField.all(annotated)
    assert len(fields) == 1
    assert isinstance(fields[0], String)
