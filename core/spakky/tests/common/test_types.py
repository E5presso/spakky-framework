from typing import Optional, Union

from spakky.core.common.types import get_callable_methods, is_optional, remove_none


def test_is_optional() -> None:
    """타입이 Optional인지 여부를 정확히 판별함을 검증한다."""
    assert is_optional(str | None) is True
    assert is_optional(Optional[str]) is True
    assert is_optional(str) is False

    assert is_optional(str | int | None) is True
    assert is_optional(Optional[Union[str, int]]) is True
    assert is_optional(Union[str, int]) is False


def test_remove_none() -> None:
    """Union 타입에서 None을 제거한 타입을 올바르게 반환함을 검증한다."""
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
    """일반 메서드가 get_callable_methods 결과에 포함됨을 검증한다."""

    class Sample:
        def method(self) -> str:
            return "value"

    obj = Sample()
    methods = get_callable_methods(obj)
    method_names = [name for name, _ in methods]

    assert "method" in method_names


def test_get_callable_methods_excludes_properties() -> None:
    """프로퍼티가 get_callable_methods 결과에서 제외됨을 검증한다."""

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
    """getattr 시 예외를 발생시키는 멤버가 건너뛰어짐을 검증한다."""

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
    """호출 불가능한 속성이 get_callable_methods 결과에서 제외됨을 검증한다."""

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
    """반환된 메서드가 객체에 바인딩되어 있음을 검증한다."""

    class Sample:
        def method(self) -> str:
            return "bound"

    obj = Sample()
    methods = get_callable_methods(obj)
    method_dict = dict(methods)

    assert "method" in method_dict
    assert method_dict["method"]() == "bound"


def test_remove_none_with_no_non_none_args() -> None:
    """None만 포함하는 Union에 대해 remove_none이 정상 동작함을 검증한다."""
    # This is a theoretical case - Union[None] or None itself
    result = remove_none(type(None))
    assert result is type(None)


def test_remove_none_with_union_of_none() -> None:
    """다양한 Union 타입에서 remove_none이 정상 동작함을 검증한다."""
    # Test Union[int, str, None] -> Union[int, str]
    result = remove_none(Union[int, str, None])
    # Union comparison needs ==, not is
    assert result == Union[int, str]  # noqa: E721

    # Test Union[int, None] -> int
    result = remove_none(Union[int, None])
    assert result is int
