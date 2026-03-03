from spakky.core.utils.inspection import has_default_constructor, is_instance_method


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
