from typing import Optional, Union

from spakky.core.types import is_optional, remove_none


def test_is_optional() -> None:
    assert is_optional(str | None) is True
    assert is_optional(Optional[str]) is True
    assert is_optional(str) is False

    assert is_optional(str | int | None) is True
    assert is_optional(Optional[Union[str, int]]) is True
    assert is_optional(Union[str, int]) is False


def test_remove_none() -> None:
    """Test remove_none function"""
    # Remove None from Union types
    assert remove_none(str | None) is str
    assert remove_none(Optional[str]) is str
    assert remove_none(str | int | None) == Union[str, int]

    # Non-optional types should remain unchanged
    assert remove_none(str) is str
    assert remove_none(int) is int

    # Union of only None should return None type
    assert remove_none(type(None)) is type(None)
