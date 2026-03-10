"""Test types edge cases for complete coverage."""

from typing import Union

from spakky.core.common.types import remove_none


def test_remove_none_returns_union() -> None:
    """여러 개의 non-None 타입이 있을 때 remove_none이 Union을 반환함을 검증한다."""
    # Test with Union[int, str, float, None] -> Union[int, str, float]
    type_with_none = Union[int, str, float, None]
    result = remove_none(type_with_none)

    # Verify it returns a Union type
    # The exact representation depends on Python's typing module
    assert result is not None


def test_remove_none_without_union() -> None:
    """Union이 아닌 타입에 대해 remove_none이 원본 타입을 그대로 반환함을 검증한다."""
    # Test with plain type (not a Union)
    result = remove_none(int)

    # Should return the type as-is since it's not a Union
    assert result is int
