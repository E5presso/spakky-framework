"""Tests for Index constraint metadata."""

from typing import Annotated, cast

from spakky.core.common.metadata import AnnotatedType

from spakky.plugins.sqlalchemy.orm.constraints.index import Index
from spakky.plugins.sqlalchemy.orm.fields.string import String


def test_index_default_name_expect_none() -> None:
    """Index의 기본 name 값이 None인지 검증한다."""
    idx = Index()
    assert idx.name is None


def test_index_default_unique_expect_false() -> None:
    """Index의 기본 unique 값이 False인지 검증한다."""
    idx = Index()
    assert idx.unique is False


def test_index_custom_name_expect_value() -> None:
    """Index에 커스텀 name을 설정할 수 있는지 검증한다."""
    idx = Index(name="idx_user_email")
    assert idx.name == "idx_user_email"


def test_index_unique_true_expect_true() -> None:
    """Index의 unique를 True로 설정할 수 있는지 검증한다."""
    idx = Index(unique=True)
    assert idx.unique is True


def test_index_with_all_options_expect_correct_values() -> None:
    """Index에 모든 옵션을 설정했을 때 값이 올바른지 검증한다."""
    idx = Index(name="idx_unique_username", unique=True)
    assert idx.name == "idx_unique_username"
    assert idx.unique is True


def test_index_get_from_annotated_expect_instance() -> None:
    """Annotated 타입에서 Index 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(
        AnnotatedType, Annotated[str, String(length=255), Index(name="idx_email")]
    )
    idx = Index.get(annotated)
    assert isinstance(idx, Index)
    assert idx.name == "idx_email"


def test_index_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 Index가 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[str, String(), Index()])
    assert Index.exists(annotated) is True


def test_index_not_exists_in_annotated_expect_false() -> None:
    """Annotated 타입에 Index가 없을 때 exists()가 False를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[str, String()])
    assert Index.exists(annotated) is False


def test_index_get_or_none_when_exists_expect_instance() -> None:
    """Index가 있을 때 get_or_none()이 인스턴스를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[str, String(), Index(unique=True)])
    result = Index.get_or_none(annotated)
    assert result is not None
    assert result.unique is True


def test_index_get_or_none_when_not_exists_expect_none() -> None:
    """Index가 없을 때 get_or_none()이 None을 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[str, String()])
    result = Index.get_or_none(annotated)
    assert result is None


def test_index_mutability_expect_mutable() -> None:
    """Index 인스턴스가 mutable인지 검증한다."""
    idx = Index()
    idx.unique = True
    assert idx.unique
    idx.name = "idx_updated"
    assert idx.name == "idx_updated"
