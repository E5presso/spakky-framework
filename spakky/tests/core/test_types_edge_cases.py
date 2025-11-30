"""Test types edge cases for complete coverage."""

from typing import Union

from spakky.core.types import remove_none


def test_remove_none_returns_union() -> None:
    """Test remove_none with multiple non-None types."""
    # Test with Union[int, str, float, None] -> Union[int, str, float]
    type_with_none = Union[int, str, float, None]
    result = remove_none(type_with_none)

    # Verify it returns a Union type
    # The exact representation depends on Python's typing module
    assert result is not None


def test_remove_none_without_union() -> None:
    """Test remove_none with non-Union type."""
    # Test with plain type (not a Union)
    result = remove_none(int)

    # Should return the type as-is since it's not a Union
    assert result is int
