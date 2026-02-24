from typing import Optional, Union

from spakky.core.common.types import get_callable_methods, is_optional, remove_none


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


def test_get_callable_methods_includes_regular_methods() -> None:
    """Regular methods should be included in the result."""

    class Sample:
        def method(self) -> str:
            return "value"

    obj = Sample()
    methods = get_callable_methods(obj)
    method_names = [name for name, _ in methods]

    assert "method" in method_names


def test_get_callable_methods_excludes_properties() -> None:
    """Properties should be excluded from the result."""

    class Sample:
        @property
        def prop(self) -> str:
            raise RuntimeError("Property getter should not be called!")

        def method(self) -> str:
            return "value"

    obj = Sample()
    methods = get_callable_methods(obj)
    method_names = [name for name, _ in methods]

    assert "prop" not in method_names
    assert "method" in method_names


def test_get_callable_methods_skips_on_getattr_exception() -> None:
    """Members that raise exceptions on getattr should be skipped."""

    class ProblematicDescriptor:
        """Descriptor that raises an exception on access."""

        def __get__(self, obj: object, objtype: type | None = None) -> str:
            raise AttributeError("Cannot access this attribute")

    class Sample:
        problematic = ProblematicDescriptor()

        def method(self) -> str:
            return "value"

    obj = Sample()
    methods = get_callable_methods(obj)
    method_names = [name for name, _ in methods]

    assert "problematic" not in method_names
    assert "method" in method_names


def test_get_callable_methods_excludes_non_callable_attributes() -> None:
    """Non-callable attributes should be excluded from the result."""

    class Sample:
        data: str = "not callable"

        def method(self) -> str:
            return "value"

    obj = Sample()
    methods = get_callable_methods(obj)
    method_names = [name for name, _ in methods]

    assert "data" not in method_names
    assert "method" in method_names


def test_get_callable_methods_returns_bound_methods() -> None:
    """Returned methods should be bound to the object."""

    class Sample:
        def method(self) -> str:
            return "bound"

    obj = Sample()
    methods = get_callable_methods(obj)
    method_dict = dict(methods)

    assert "method" in method_dict
    assert method_dict["method"]() == "bound"


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
