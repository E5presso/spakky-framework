import pytest
from spakky.core.common.mutability import immutable

from spakky.domain.models.value_object import AbstractValueObject


def test_value_object_equals() -> None:
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
    @immutable
    class _(AbstractValueObject):
        name: str
        age: int
        jobs: frozenset[str]

        def validate(self) -> None:
            return


def test_value_object_can_only_composed_by_hashable_objects_expect_error() -> None:
    with pytest.raises(TypeError, match="type of 'jobs' is not hashable"):

        @immutable
        class _(AbstractValueObject):
            name: str
            age: int
            jobs: list[str]

            def validate(self) -> None:
                return


def test_value_object_hash_order_sensitive() -> None:
    """Test that hash is sensitive to attribute order (not XOR-based)."""

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
    """Test that value objects work correctly as set elements."""

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
