"""Tests for PrimaryKey constraint metadata."""

from typing import Annotated, cast

from spakky.core.common.metadata import AnnotatedType

from spakky.plugins.sqlalchemy.orm.constraints.primary_key import PrimaryKey
from spakky.plugins.sqlalchemy.orm.fields.numeric import Integer


def test_primary_key_default_autoincrement_expect_false() -> None:
    """PrimaryKey의 기본 autoincrement 값이 False인지 검증한다."""
    pk = PrimaryKey()
    assert pk.autoincrement is False


def test_primary_key_autoincrement_true_expect_true() -> None:
    """PrimaryKey의 autoincrement를 True로 설정할 수 있는지 검증한다."""
    pk = PrimaryKey(autoincrement=True)
    assert pk.autoincrement is True


def test_primary_key_get_from_annotated_expect_instance() -> None:
    """Annotated 타입에서 PrimaryKey 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(
        AnnotatedType, Annotated[int, Integer(), PrimaryKey(autoincrement=True)]
    )
    pk = PrimaryKey.get(annotated)
    assert isinstance(pk, PrimaryKey)
    assert pk.autoincrement is True


def test_primary_key_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 PrimaryKey가 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[int, Integer(), PrimaryKey()])
    assert PrimaryKey.exists(annotated) is True


def test_primary_key_not_exists_in_annotated_expect_false() -> None:
    """Annotated 타입에 PrimaryKey가 없을 때 exists()가 False를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[int, Integer()])
    assert PrimaryKey.exists(annotated) is False


def test_primary_key_get_or_none_when_exists_expect_instance() -> None:
    """PrimaryKey가 있을 때 get_or_none()이 인스턴스를 반환하는지 검증한다."""
    annotated = cast(
        AnnotatedType, Annotated[int, Integer(), PrimaryKey(autoincrement=True)]
    )
    result = PrimaryKey.get_or_none(annotated)
    assert result is not None
    assert result.autoincrement is True


def test_primary_key_get_or_none_when_not_exists_expect_none() -> None:
    """PrimaryKey가 없을 때 get_or_none()이 None을 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[int, Integer()])
    result = PrimaryKey.get_or_none(annotated)
    assert result is None


def test_primary_key_mutability_expect_mutable() -> None:
    """PrimaryKey 인스턴스가 mutable인지 검증한다."""
    pk = PrimaryKey()
    pk.autoincrement = True
    assert pk.autoincrement is True
