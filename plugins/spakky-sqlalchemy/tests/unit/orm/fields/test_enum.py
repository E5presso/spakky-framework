"""Tests for Enum field metadata."""

from enum import Enum as PyEnum
from typing import Annotated, cast

from spakky.core.common.metadata import AnnotatedType

from spakky.plugins.sqlalchemy.orm.fields.enum import Enum


class SampleRole(PyEnum):
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


class SampleStatus(PyEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


def test_enum_with_enum_class_expect_correct_class() -> None:
    """Enum 필드에 enum_class를 설정했을 때 올바르게 저장되는지 검증한다."""
    field = Enum(enum_class=SampleRole)
    assert field.enum_class is SampleRole


def test_enum_default_native_enum_expect_true() -> None:
    """Enum 필드의 기본 native_enum 값이 True인지 검증한다."""
    field = Enum(enum_class=SampleRole)
    assert field.native_enum is True


def test_enum_native_enum_false_expect_false() -> None:
    """Enum 필드의 native_enum을 False로 설정할 수 있는지 검증한다."""
    field = Enum(enum_class=SampleRole, native_enum=False)
    assert field.native_enum is False


def test_enum_get_from_annotated_expect_instance() -> None:
    """Annotated 타입에서 Enum 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[SampleRole, Enum(enum_class=SampleRole)])
    field = Enum.get(annotated)
    assert isinstance(field, Enum)
    assert field.enum_class is SampleRole


def test_enum_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 Enum이 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(
        AnnotatedType, Annotated[SampleStatus, Enum(enum_class=SampleStatus)]
    )
    assert Enum.exists(annotated) is True


def test_enum_with_all_options_expect_correct_values() -> None:
    """Enum 필드에 모든 옵션을 설정했을 때 값이 올바른지 검증한다."""
    field = Enum(
        enum_class=SampleRole,
        native_enum=False,
        nullable=False,
        name="role_col",
        comment="User role",
    )
    assert field.enum_class is SampleRole
    assert field.native_enum is False
    assert field.nullable is False
    assert field.name == "role_col"
    assert field.comment == "User role"


def test_enum_inherits_abstract_field_defaults() -> None:
    """Enum 필드가 AbstractField의 기본값을 올바르게 상속하는지 검증한다."""
    field = Enum(enum_class=SampleRole)
    assert field.nullable is True
    assert field.default is None
    assert field.default_factory is None
    assert field.name == ""
    assert field.comment is None


def test_enum_with_different_enum_classes_expect_distinct() -> None:
    """서로 다른 enum_class를 사용한 Enum 필드가 구별되는지 검증한다."""
    field_role = Enum(enum_class=SampleRole)
    field_status = Enum(enum_class=SampleStatus)
    assert field_role.enum_class is not field_status.enum_class
