import pytest
from spakky.core.common.mutability import immutable

from spakky.domain.models.value_object import (
    AbstractValueObject,
    UnhashableFieldTypeError,
)


def test_value_object_equals() -> None:
    """동일한 속성을 가진 값 객체가 동등함을 검증한다."""

    @immutable
    class SampleValueObject(AbstractValueObject):
        name: str
        age: int

        def validate(self) -> None:
            return

    value_object1: SampleValueObject = SampleValueObject(name="John", age=30)
    value_object2: SampleValueObject = SampleValueObject(name="John", age=30)
    assert value_object1 == value_object2


def test_value_object_not_equals() -> None:
    """다른 속성을 가진 값 객체가 동등하지 않음을 검증한다."""

    @immutable
    class SampleValueObject(AbstractValueObject):
        name: str
        age: int

        def validate(self) -> None:
            return

    value_object1: SampleValueObject = SampleValueObject(name="John", age=30)
    value_object2: SampleValueObject = SampleValueObject(name="Sarah", age=30)
    assert value_object1 != value_object2


def test_value_object_not_equals_with_wrong_type() -> None:
    """다른 타입의 값 객체가 동등하지 않음을 검증한다."""

    @immutable
    class SampleValueObject(AbstractValueObject):
        name: str
        age: int

        def validate(self) -> None:
            return

    @immutable
    class AnotherValueObject(AbstractValueObject):
        name: str
        age: int

        def validate(self) -> None:
            return

    value_object1: SampleValueObject = SampleValueObject(name="John", age=30)
    value_object2: AnotherValueObject = AnotherValueObject(name="Sarah", age=30)
    assert value_object1 != value_object2


def test_value_object_clone() -> None:
    """값 객체를 복제하면 동등한 객체가 생성됨을 검증한다."""

    @immutable
    class SampleValueObject(AbstractValueObject):
        name: str
        age: int

        def validate(self) -> None:
            return

    value_object1: SampleValueObject = SampleValueObject(name="John", age=30)
    value_object2: SampleValueObject = value_object1.clone()
    assert value_object1 == value_object2


def test_value_object_hash() -> None:
    """동일한 값 객체가 동일한 해시값을 가짐을 검증한다."""

    @immutable
    class SampleValueObject(AbstractValueObject):
        name: str
        age: int

        def validate(self) -> None:
            return

    value_object1: SampleValueObject = SampleValueObject(name="John", age=30)
    value_object2: SampleValueObject = SampleValueObject(name="John", age=30)
    assert hash(value_object1) == hash(value_object2)


def test_value_object_can_only_composed_by_hashable_objects_expect_success() -> None:
    """해시 가능한 타입으로만 구성된 값 객체가 정상적으로 생성됨을 검증한다."""

    @immutable
    class _(AbstractValueObject):
        name: str
        age: int
        jobs: frozenset[str]

        def validate(self) -> None:
            return


def test_value_object_can_only_composed_by_hashable_objects_expect_error() -> None:
    """해시 불가능한 타입을 포함한 값 객체 생성 시 UnhashableFieldTypeError가 발생함을 검증한다."""
    with pytest.raises(
        UnhashableFieldTypeError, match="Value object field type is not hashable."
    ) as exc_info:

        @immutable
        class _(AbstractValueObject):
            name: str
            age: int
            jobs: list

            def validate(self) -> None:
                return

    assert exc_info.value.field_name == "jobs"


def test_value_object_hash_order_sensitive() -> None:
    """해시가 속성 순서에 민감함을 검증한다 (XOR 기반이 아님)."""

    @immutable
    class Pair(AbstractValueObject):
        first: int
        second: int

        def validate(self) -> None:
            return

    # Different order should produce different hashes
    pair1 = Pair(first=1, second=2)
    pair2 = Pair(first=2, second=1)

    assert pair1 != pair2, "Value objects with different values should not be equal"
    assert hash(pair1) != hash(pair2), "Hash should be order-sensitive"


def test_value_object_hash_in_set() -> None:
    """값 객체가 set의 요소로 올바르게 동작함을 검증한다."""

    @immutable
    class Point(AbstractValueObject):
        x: int
        y: int

        def validate(self) -> None:
            return

    point1 = Point(x=1, y=2)
    point2 = Point(x=1, y=2)
    point3 = Point(x=2, y=1)

    points = {point1, point2, point3}

    # point1 and point2 are equal, so set should contain only 2 elements
    assert len(points) == 2
    assert point1 in points
    assert point2 in points
    assert point3 in points
