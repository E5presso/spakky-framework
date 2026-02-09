"""Tests for Unique constraint metadata."""

from typing import Annotated, cast

from spakky.core.common.metadata import AnnotatedType

from spakky.plugins.sqlalchemy.orm.constraints.unique import Unique
from spakky.plugins.sqlalchemy.orm.fields.string import String


def test_unique_default_name_expect_none() -> None:
    """Unique의 기본 name 값이 None인지 검증한다."""
    uq = Unique()
    assert uq.name is None


def test_unique_custom_name_expect_value() -> None:
    """Unique에 커스텀 name을 설정할 수 있는지 검증한다."""
    uq = Unique(name="uq_user_email")
    assert uq.name == "uq_user_email"


def test_unique_get_from_annotated_expect_instance() -> None:
    """Annotated 타입에서 Unique 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(
        AnnotatedType, Annotated[str, String(length=255), Unique(name="uq_email")]
    )
    uq = Unique.get(annotated)
    assert isinstance(uq, Unique)
    assert uq.name == "uq_email"


def test_unique_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 Unique가 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[str, String(), Unique()])
    assert Unique.exists(annotated) is True


def test_unique_not_exists_in_annotated_expect_false() -> None:
    """Annotated 타입에 Unique가 없을 때 exists()가 False를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[str, String()])
    assert Unique.exists(annotated) is False


def test_unique_get_or_none_when_exists_expect_instance() -> None:
    """Unique가 있을 때 get_or_none()이 인스턴스를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[str, String(), Unique(name="uq_test")])
    result = Unique.get_or_none(annotated)
    assert result is not None
    assert result.name == "uq_test"


def test_unique_get_or_none_when_not_exists_expect_none() -> None:
    """Unique가 없을 때 get_or_none()이 None을 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[str, String()])
    result = Unique.get_or_none(annotated)
    assert result is None


def test_unique_mutability_expect_mutable() -> None:
    """Unique 인스턴스가 mutable인지 검증한다."""
    uq = Unique()
    uq.name = "uq_updated"
    assert uq.name == "uq_updated"
