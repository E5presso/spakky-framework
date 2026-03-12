from spakky.core.utils.inspection import (
    get_fully_qualified_name,
    has_default_constructor,
    is_instance_method,
)


def test_is_instance_method() -> None:
    """인스턴스 메서드와 일반 함수를 올바르게 구분하는지 검증한다."""

    def func() -> str:
        return "Hello, World!"

    class A:
        def method(self) -> str:
            return "Hello, World!"

    assert is_instance_method(A().method) is True
    assert is_instance_method(func) is False


def test_has_default_constructor() -> None:
    """클래스가 기본 생성자를 가지는지 올바르게 판단하는지 검증한다."""

    class A:
        def __init__(self) -> None:
            pass

    class B:
        pass

    assert has_default_constructor(A) is False
    assert has_default_constructor(B) is True


def test_has_default_constructor_with_protocol() -> None:
    """프로토콜 클래스에서도 기본 생성자 판단이 올바르게 동작하는지 검증한다."""

    class A:
        def __init__(self) -> None:
            pass

    class B:
        pass

    assert has_default_constructor(A) is False
    assert has_default_constructor(B) is True


def test_get_fully_qualified_name_with_class() -> None:
    """클래스의 FQCN을 올바르게 반환하는지 검증한다."""

    class MyClass:
        pass

    fqcn = get_fully_qualified_name(MyClass)
    assert fqcn.endswith(MyClass.__qualname__)


def test_get_fully_qualified_name_with_method() -> None:
    """메서드의 FQCN을 올바르게 반환하는지 검증한다."""

    class MyClass:
        def my_method(self) -> None:
            pass

    fqcn = get_fully_qualified_name(MyClass.my_method)
    assert fqcn.endswith(MyClass.my_method.__qualname__)


def test_get_fully_qualified_name_with_function() -> None:
    """함수의 FQCN을 올바르게 반환하는지 검증한다."""

    def my_function() -> None:
        pass

    fqcn = get_fully_qualified_name(my_function)
    assert fqcn.endswith(my_function.__qualname__)


def test_get_fully_qualified_name_with_instance() -> None:
    """인스턴스의 FQCN을 클래스 이름으로 반환하는지 검증한다."""

    class MyClass:
        pass

    instance = MyClass()
    fqcn = get_fully_qualified_name(instance)
    assert fqcn.endswith(MyClass.__qualname__)
