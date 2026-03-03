from abc import abstractmethod
from dataclasses import dataclass
from typing import Annotated, Any, Protocol, TypeVar, cast

import pytest

from spakky.core.pod.annotations.pod import (
    CannotDeterminePodTypeError,
    CannotUseVarArgsInPodError,
    DependencyInfo,
    Pod,
    is_class_pod,
    is_function_pod,
)
from spakky.core.pod.annotations.qualifier import Qualifier


def test_pod_issubclass_of() -> None:
    """Pod의 is_family_with 메서드가 부모 클래스와의 상속 관계를 올바르게 판단함을 검증한다."""

    class A: ...

    @Pod()
    class B(A): ...

    @Pod()
    class C(A): ...

    assert Pod.get(B).is_family_with(A) is True
    assert Pod.get(C).is_family_with(A) is True


def test_pod_issubclass_of_with_generic() -> None:
    """Pod의 is_family_with 메서드가 제네릭 타입과의 상속 관계를 올바르게 판단함을 검증한다."""
    T_contra = TypeVar("T_contra", contravariant=True)

    class IA(Protocol[T_contra]):
        @abstractmethod
        def do(self, t: T_contra) -> None: ...

    @Pod()
    class B(IA[int]):
        def do(self, t: int) -> None:
            return

    @Pod()
    class C(IA[str]):
        def do(self, t: str) -> None:
            return

    assert Pod.get(B).is_family_with(IA) is False
    assert Pod.get(C).is_family_with(IA) is False
    assert Pod.get(B).is_family_with(IA[int]) is True
    assert Pod.get(C).is_family_with(IA[str]) is True


def test_pod_instantiate() -> None:
    """Pod의 instantiate 메서드가 의존성을 주입하여 인스턴스를 생성함을 검증한다."""

    @Pod()
    class A:
        def __init__(self, a: int) -> None:
            self.a = a

    a: A = cast(A, Pod.get(A).instantiate({"a": 1}))
    assert a.a == 1


def test_pod_instantiate_with_default_value() -> None:
    """Pod의 instantiate 메서드가 기본값을 가진 의존성을 올바르게 처리함을 검증한다."""

    @Pod()
    class A:
        def __init__(self, name: str, age: int = 30) -> None:
            self.name = name
            self.age = age

    a1: A = cast(A, Pod.get(A).instantiate({"name": "John"}))
    assert a1.name == "John"
    assert a1.age == 30

    a2: A = cast(A, Pod.get(A).instantiate({"name": "John", "age": 40}))
    assert a2.name == "John"
    assert a2.age == 40

    a3: A = cast(A, Pod.get(A).instantiate({"name": "John", "age": None}))
    assert a3.name == "John"
    assert a3.age == 30


def test_is_class_pod() -> None:
    """is_class_pod 함수가 클래스와 함수를 올바르게 구분함을 검증한다."""

    class A: ...

    def a() -> None: ...

    assert is_class_pod(A) is True
    assert is_class_pod(a) is False


def test_is_function_pod() -> None:
    """is_function_pod 함수가 함수와 클래스를 올바르게 구분함을 검증한다."""

    class A: ...

    def a() -> None: ...

    assert is_function_pod(A) is False
    assert is_function_pod(a) is True


def test_pod() -> None:
    """@Pod 데코레이터가 클래스에 Pod 메타데이터를 올바르게 설정함을 검증한다."""

    @Pod()
    class SampleClass:
        name: str
        age: int

        def __init__(self, name: str, age: int) -> None:
            self.name = name
            self.age = age

    assert Pod.get(SampleClass).dependencies == {
        "name": DependencyInfo(name="name", type_=str),
        "age": DependencyInfo(name="age", type_=int),
    }
    assert Pod.get(SampleClass).name == "sample_class"
    sample: SampleClass = SampleClass(name="John", age=30)
    assert sample.name == "John"
    assert sample.age == 30


def test_pod_with_var_args() -> None:
    """@Pod 데코레이터가 *args, **kwargs를 사용한 클래스에 예외를 발생시킴을 검증한다."""
    with pytest.raises(CannotUseVarArgsInPodError):

        @Pod()
        class _:
            name: str
            age: int

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self.name = args[0] or kwargs["name"]
                self.age = args[1] or kwargs["age"]


def test_pod_factory_with_var_args() -> None:
    """@Pod 데코레이터가 *args, **kwargs를 사용한 팩토리 함수에 예외를 발생시킴을 검증한다."""
    with pytest.raises(CannotUseVarArgsInPodError):

        @Pod()
        def _(*args: Any, **kwargs: Any) -> Any:
            return args[0] or kwargs["name"]


def test_pod_factory_with_return_annotation() -> None:
    """@Pod 데코레이터가 반환 타입 어노테이션이 있는 팩토리 함수를 올바르게 처리함을 검증한다."""

    class A: ...

    @Pod()
    def get_a() -> A:
        return A()

    assert Pod.exists(get_a) is True
    assert Pod.get(get_a) is not None
    assert Pod.get(get_a).name == "get_a"
    assert Pod.get(get_a).type_ is A


def test_pod_factory_without_return_annotation() -> None:
    """@Pod 데코레이터가 반환 타입 어노테이션이 없는 팩토리 함수에 예외를 발생시킴을 검증한다."""

    class A: ...

    with pytest.raises(CannotDeterminePodTypeError):

        @Pod()
        def _():
            return A()


def test_pod_with_scope() -> None:
    """@Pod 데코레이터의 scope 파라미터가 올바르게 설정됨을 검증한다."""

    @Pod(scope=Pod.Scope.PROTOTYPE)
    class A: ...

    assert Pod.exists(A) is True
    assert Pod.get(A) is not None
    assert Pod.get(A).scope is Pod.Scope.PROTOTYPE


def test_pod_factory_with_scope() -> None:
    """@Pod 데코레이터의 scope 파라미터가 팩토리 함수에도 올바르게 적용됨을 검증한다."""

    class A: ...

    @Pod(scope=Pod.Scope.PROTOTYPE)
    def get_a() -> A:
        return A()

    assert Pod.exists(get_a) is True
    assert Pod.get(get_a) is not None
    assert Pod.get(get_a).name == "get_a"
    assert Pod.get(get_a).type_ is A
    assert Pod.get(get_a).scope is Pod.Scope.PROTOTYPE


def test_pod_with_name() -> None:
    """@Pod 데코레이터의 name 파라미터가 올바르게 설정됨을 검증한다."""

    @Pod(name="asdf")
    class A: ...

    assert Pod.exists(A) is True
    assert Pod.get(A) is not None
    assert Pod.get(A).name == "asdf"


def test_pod_factory_with_name() -> None:
    """@Pod 데코레이터의 name 파라미터가 팩토리 함수에도 올바르게 적용됨을 검증한다."""

    class A: ...

    @Pod(name="a")
    def get_a() -> A:
        return A()

    assert Pod.exists(get_a) is True
    assert Pod.get(get_a) is not None
    assert Pod.get(get_a).name == "a"
    assert Pod.get(get_a).type_ is A


def test_pod_with_qualifier() -> None:
    """@Pod 데코레이터가 Qualifier 어노테이션을 올바르게 파싱함을 검증한다."""

    def is_dummy_pod(pod: Pod) -> bool:
        return pod.name == "dummy_pod"

    def is_primary_pod(pod: Pod) -> bool:
        return pod.is_primary

    @Pod()
    @dataclass
    class A:
        name: Annotated[str, Qualifier(is_dummy_pod), "dummy", 30]

    @Pod()
    class B:
        __name: str
        __age: int
        __job: str

        def __init__(
            self,
            name: Annotated[str, Qualifier(is_primary_pod), "other", True, None],
            age: Annotated[int, Qualifier(is_primary_pod), "other", True, None],
            job: str,
        ) -> None:
            self.__name = name
            self.__age = age
            self.__job = job

        def b(self) -> str:
            return f"{self.__name}({self.__job}) is {self.__age} years old"

    assert Pod.get(A).dependencies == {
        "name": DependencyInfo(
            name="name",
            type_=str,
            qualifiers=[Qualifier(is_dummy_pod)],
        ),
    }
    assert Pod.get(B).dependencies == {
        "name": DependencyInfo(
            name="name",
            type_=str,
            qualifiers=[Qualifier(is_primary_pod)],
        ),
        "age": DependencyInfo(
            name="age",
            type_=int,
            qualifiers=[Qualifier(is_primary_pod)],
        ),
        "job": DependencyInfo(name="job", type_=str),
    }


def test_pod_equality_with_different_type() -> None:
    """Pod의 __eq__ 메서드가 Pod가 아닌 타입과 비교 시 False를 반환함을 검증한다."""

    @Pod(name="test_pod")
    class TestClass: ...

    pod = Pod.get(TestClass)
    # Test equality with string
    assert pod != "test_pod"
    # Test equality with int
    assert pod != 123
    # Test equality with None
    assert pod != None  # noqa: E711


def test_pod_equality_with_same_name_expect_true() -> None:
    """같은 이름의 두 Pod이 동등함을 검증한다."""

    @Pod(name="same_name")
    class FirstClass: ...

    @Pod(name="same_name")
    class SecondClass: ...

    first_pod = Pod.get(FirstClass)
    second_pod = Pod.get(SecondClass)

    # 같은 이름이면 동등 (line 247: return self.name == value.name)
    assert first_pod == second_pod


def test_pod_equality_with_different_name_expect_false() -> None:
    """다른 이름의 두 Pod이 동등하지 않음을 검증한다."""

    @Pod(name="first_name")
    class FirstClass: ...

    @Pod(name="second_name")
    class SecondClass: ...

    first_pod = Pod.get(FirstClass)
    second_pod = Pod.get(SecondClass)

    assert first_pod != second_pod
