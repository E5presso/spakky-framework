"""Test core types for complete coverage."""

from typing import Union

from spakky.core.types import remove_none


def test_remove_none_with_no_non_none_args() -> None:
    """Test remove_none with Union that only contains None."""
    # This is a theoretical case - Union[None] or None itself
    result = remove_none(type(None))
    assert result is type(None)


def test_remove_none_with_union_of_none() -> None:
    """Test remove_none with various Union types."""
    # Test Union[int, str, None] -> Union[int, str]
    result = remove_none(Union[int, str, None])
    # Union comparison needs ==, not is
    assert result == Union[int, str]  # noqa: E721

    # Test Union[int, None] -> int
    result = remove_none(Union[int, None])
    assert result is int
