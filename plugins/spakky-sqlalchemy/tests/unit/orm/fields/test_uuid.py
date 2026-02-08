"""Tests for UUID field metadata."""

from typing import Annotated, cast
from uuid import UUID

from spakky.core.common.metadata import AnnotatedType

from spakky.plugins.sqlalchemy.orm.fields.uuid import Uuid


def test_uuid_default_as_uuid_expect_true() -> None:
    """Uuid 필드의 기본 as_uuid 값이 True인지 검증한다."""
    field = Uuid()
    assert field.as_uuid is True


def test_uuid_as_uuid_false_expect_false() -> None:
    """Uuid 필드의 as_uuid를 False로 설정할 수 있는지 검증한다."""
    field = Uuid(as_uuid=False)
    assert field.as_uuid is False


def test_uuid_get_from_annotated_expect_instance() -> None:
    """Annotated 타입에서 Uuid 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[UUID, Uuid()])
    field = Uuid.get(annotated)
    assert isinstance(field, Uuid)


def test_uuid_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 Uuid가 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[UUID, Uuid()])
    assert Uuid.exists(annotated) is True


def test_uuid_with_all_options_expect_correct_values() -> None:
    """Uuid 필드에 모든 옵션을 설정했을 때 값이 올바른지 검증한다."""
    field = Uuid(
        as_uuid=True,
        nullable=False,
        name="user_uuid",
        comment="User unique identifier",
    )
    assert field.as_uuid is True
    assert field.nullable is False
    assert field.name == "user_uuid"
    assert field.comment == "User unique identifier"


def test_uuid_inherits_abstract_field_defaults() -> None:
    """Uuid 필드가 AbstractField의 기본값을 올바르게 상속하는지 검증한다."""
    field = Uuid()
    assert field.nullable is True
    assert field.default is None
    assert field.default_factory is None
    assert field.name == ""
    assert field.comment is None
