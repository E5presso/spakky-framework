import inspect
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from spakky.core.common.annotation import (
    Annotation,
    AnnotationNotFoundError,
    ClassAnnotation,
    FunctionAnnotation,
    MultipleAnnotationFoundError,
)


def test_class_annotation_expect_success() -> None:
    """클래스 어노테이션이 정상적으로 적용되고 조회될 수 있음을 검증한다."""

    @ClassAnnotation()
    class Dummy: ...

    assert ClassAnnotation.exists(Dummy)
    assert ClassAnnotation.get_or_none(Dummy) is not None
    assert ClassAnnotation.get_or_default(Dummy, ClassAnnotation()) is not None
    assert ClassAnnotation.get(Dummy)


def test_class_annotation_expect_fail() -> None:
    """어노테이션이 없는 클래스에서 조회 시 적절한 예외가 발생함을 검증한다."""

    class Dummy: ...

    with pytest.raises(AssertionError):
        assert ClassAnnotation.exists(Dummy)
    with pytest.raises(AssertionError):
        assert ClassAnnotation.get_or_none(Dummy) is not None
    with pytest.raises(AnnotationNotFoundError):
        ClassAnnotation.get(Dummy)


def test_multiple_class_annotation_expect_success() -> None:
    """여러 종류의 클래스 어노테이션을 동시에 적용할 수 있음을 검증한다."""

    @dataclass
    class DummyAnnotation(ClassAnnotation): ...

    @dataclass
    class AnotherAnnotation(ClassAnnotation): ...

    @DummyAnnotation()
    @AnotherAnnotation()
    class Dummy: ...

    assert DummyAnnotation.exists(Dummy)
    assert AnotherAnnotation.exists(Dummy)


def test_same_class_annotation_multiple_times_expect_error() -> None:
    """동일한 어노테이션을 여러 번 적용 시 MultipleAnnotationFoundError가 발생함을 검증한다."""

    @dataclass
    class DummyAnnotation(ClassAnnotation):
        age: int

    @DummyAnnotation(age=29)
    @DummyAnnotation(age=30)
    class Dummy: ...

    with pytest.raises(MultipleAnnotationFoundError):
        DummyAnnotation.get(Dummy)
    with pytest.raises(MultipleAnnotationFoundError):
        DummyAnnotation.get_or_none(Dummy)
    with pytest.raises(MultipleAnnotationFoundError):
        DummyAnnotation.get_or_default(Dummy, DummyAnnotation(age=30))

    assert DummyAnnotation.all(Dummy) == [
        DummyAnnotation(age=30),
        DummyAnnotation(age=29),
    ]


def test_function_passing_type_hint() -> None:
    """함수 어노테이션 적용 후에도 원본 함수의 시그니처가 유지됨을 검증한다."""

    @dataclass
    class CustomAnnotation(FunctionAnnotation): ...

    def func(name: str, age: int) -> tuple[str, int]:
        return name, age

    old_signature: inspect.Signature = inspect.signature(func)

    func = CustomAnnotation()(func)

    assert inspect.signature(func) == old_signature
    assert func(name="John", age=30) == ("John", 30)


def test_function_annotation_expect_success() -> None:
    """함수 어노테이션이 정상적으로 적용되고 조회될 수 있음을 검증한다."""

    @FunctionAnnotation()
    def function() -> None: ...

    assert FunctionAnnotation.exists(function)
    assert FunctionAnnotation.get_or_none(function) is not None
    assert FunctionAnnotation.get(function)

    @dataclass
    class CustomAnnotation(Annotation):
        name: str
        age: int

    @CustomAnnotation(name="John", age=30)
    @CustomAnnotation(name="Sarah", age=28)
    def sample() -> None: ...

    annotations: list[CustomAnnotation] = CustomAnnotation.all(sample)
    assert annotations == [
        CustomAnnotation(name="Sarah", age=28),
        CustomAnnotation(name="John", age=30),
    ]


def test_function_annotation_expect_fail() -> None:
    """어노테이션이 없는 함수에서 조회 시 적절한 예외가 발생함을 검증한다."""

    def function() -> None: ...

    with pytest.raises(AssertionError):
        assert FunctionAnnotation.exists(function)
    with pytest.raises(AssertionError):
        assert FunctionAnnotation.get_or_none(function) is not None
    with pytest.raises(AnnotationNotFoundError):
        FunctionAnnotation.get(function)


def test_multiple_function_annotation_expect_success() -> None:
    """여러 종류의 함수 어노테이션을 동시에 적용할 수 있음을 검증한다."""

    @dataclass
    class DummyAnnotation(FunctionAnnotation): ...

    @dataclass
    class AnotherAnnotation(FunctionAnnotation): ...

    @DummyAnnotation()
    @AnotherAnnotation()
    def function() -> None: ...

    assert DummyAnnotation.exists(function)
    assert AnotherAnnotation.exists(function)


def test_same_function_annotation_multiple_times_expect_error() -> None:
    """동일한 함수 어노테이션을 여러 번 적용 시 MultipleAnnotationFoundError가 발생함을 검증한다."""

    @dataclass
    class DummyAnnotation(FunctionAnnotation):
        name: str

    @DummyAnnotation(name="John")
    @DummyAnnotation(name="Sarah")
    def dummy() -> None: ...

    with pytest.raises(MultipleAnnotationFoundError):
        DummyAnnotation.get(dummy)
    with pytest.raises(MultipleAnnotationFoundError):
        DummyAnnotation.get_or_none(dummy)

    assert DummyAnnotation.all(dummy) == [
        DummyAnnotation(name="Sarah"),
        DummyAnnotation(name="John"),
    ]


def test_class_annotation_inheritance() -> None:
    """어노테이션 상속 시 상위 어노테이션 타입으로도 조회 가능함을 검증한다."""
    uid: UUID = uuid4()

    @dataclass(kw_only=True)
    class Foo(ClassAnnotation):
        uid: UUID

    @dataclass(kw_only=True)
    class Bar(Foo):
        name: str

    @dataclass(kw_only=True)
    class Baz(Bar): ...

    @Baz(uid=uid, name="John")
    class Dummy: ...

    assert Baz.exists(Dummy)
    assert Bar.exists(Dummy)
    assert Foo.exists(Dummy)

    assert Baz.get(Dummy).uid == uid
    assert Baz.get(Dummy).name == "John"
    assert Bar.get(Dummy).uid == uid
    assert Bar.get(Dummy).name == "John"
    assert Foo.get(Dummy).uid == uid


def test_class_annotation_inheritance_expect_fail() -> None:
    """상위 어노테이션만 적용된 경우 하위 어노테이션으로 조회가 실패함을 검증한다."""

    @dataclass(kw_only=True)
    class Foo(ClassAnnotation):
        uid: UUID

    @dataclass(kw_only=True)
    class Bar(Foo):
        name: str

    @dataclass(kw_only=True)
    class Baz(Bar): ...

    @Bar(uid=uuid4(), name="John")
    class Dummy2: ...

    assert Bar.exists(Dummy2)
    assert Foo.exists(Dummy2)
    with pytest.raises(AssertionError):
        assert Baz.exists(Dummy2)
