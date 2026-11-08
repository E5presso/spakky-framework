import copy
from collections.abc import Sequence
from dataclasses import astuple, dataclass
from typing import NamedTuple

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

    value_object1: SampleValueObject = SampleValueObject(name="John", age=30)
    value_object2: SampleValueObject = SampleValueObject(name="John", age=30)
    assert value_object1 == value_object2


def test_value_object_not_equals() -> None:
    """다른 속성을 가진 값 객체가 동등하지 않음을 검증한다."""

    @immutable
    class SampleValueObject(AbstractValueObject):
        name: str
        age: int

    value_object1: SampleValueObject = SampleValueObject(name="John", age=30)
    value_object2: SampleValueObject = SampleValueObject(name="Sarah", age=30)
    assert value_object1 != value_object2


def test_value_object_not_equals_with_wrong_type() -> None:
    """다른 타입의 값 객체가 동등하지 않음을 검증한다."""

    @immutable
    class SampleValueObject(AbstractValueObject):
        name: str
        age: int

    @immutable
    class AnotherValueObject(AbstractValueObject):
        name: str
        age: int

    value_object1: SampleValueObject = SampleValueObject(name="John", age=30)
    value_object2: AnotherValueObject = AnotherValueObject(name="Sarah", age=30)
    assert value_object1 != value_object2


def test_value_object_clone() -> None:
    """값 객체를 복제하면 동등한 객체가 생성됨을 검증한다."""

    @immutable
    class SampleValueObject(AbstractValueObject):
        name: str
        age: int

    value_object1: SampleValueObject = SampleValueObject(name="John", age=30)
    value_object2: SampleValueObject = value_object1.clone()
    assert value_object1 == value_object2


def test_value_object_hash() -> None:
    """동일한 값 객체가 동일한 해시값을 가짐을 검증한다."""

    @immutable
    class SampleValueObject(AbstractValueObject):
        name: str
        age: int

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

    assert exc_info.value.field_name == "jobs"


def test_value_object_hash_order_sensitive() -> None:
    """해시가 속성 순서에 민감함을 검증한다 (XOR 기반이 아님)."""

    @immutable
    class Pair(AbstractValueObject):
        first: int
        second: int

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

    point1 = Point(x=1, y=2)
    point2 = Point(x=1, y=2)
    point3 = Point(x=2, y=1)

    points = {point1, point2, point3}

    # point1 and point2 are equal, so set should contain only 2 elements
    assert len(points) == 2
    assert point1 in points
    assert point2 in points
    assert point3 in points


@immutable
class _Money(AbstractValueObject):
    amount: int
    currency: str


@immutable
class _Points(AbstractValueObject):
    amount: int
    currency: str


@immutable
class _Holder(AbstractValueObject):
    value: AbstractValueObject


@immutable
class _Basket(AbstractValueObject):
    items: Sequence[object]


@immutable
class _Labels(AbstractValueObject):
    # Mapping annotations fail the hashability guard; a dict still flows at runtime.
    labels: object


@dataclass(frozen=True)
class _PlainPoint:
    x: int


@dataclass(frozen=True)
class _OtherPlainPoint:
    x: int


@immutable
class _PointHolder(AbstractValueObject):
    point: object


class _Pair(NamedTuple):
    left: int
    right: int


_PARITY_CASES = [
    pytest.param(
        _Holder(value=_Money(amount=1, currency="KRW")),
        _Holder(value=_Money(amount=1, currency="KRW")),
        id="nested-value-object-equal",
    ),
    pytest.param(
        _Holder(value=_Money(amount=1, currency="KRW")),
        _Holder(value=_Money(amount=2, currency="KRW")),
        id="nested-value-object-different",
    ),
    pytest.param(
        _Holder(value=_Money(amount=1, currency="KRW")),
        _Holder(value=_Points(amount=1, currency="KRW")),
        id="nested-different-types-same-fields",
    ),
    pytest.param(
        _PointHolder(point=_PlainPoint(x=1)),
        _PointHolder(point=_OtherPlainPoint(x=1)),
        id="nested-plain-dataclass-different-types",
    ),
    pytest.param(
        _Basket(items=[1, _Money(amount=1, currency="KRW")]),
        _Basket(items=[1, _Money(amount=1, currency="KRW")]),
        id="list-with-nested-value-object",
    ),
    pytest.param(
        _Basket(items=[1, 2]),
        _Basket(items=(1, 2)),
        id="list-versus-tuple",
    ),
    pytest.param(
        _Basket(items=(_Money(amount=1, currency="KRW"),)),
        _Basket(items=(_Points(amount=1, currency="KRW"),)),
        id="tuple-with-nested-different-types",
    ),
    pytest.param(
        _Basket(items=_Pair(left=1, right=2)),
        _Basket(items=(1, 2)),
        id="namedtuple-versus-tuple",
    ),
    pytest.param(
        _Labels(labels={"a": [1, {"b": _Money(amount=1, currency="KRW")}]}),
        _Labels(labels={"a": [1, {"b": _Money(amount=1, currency="KRW")}]}),
        id="nested-dict-and-list",
    ),
    pytest.param(
        _Labels(labels={"a": 1}),
        _Labels(labels={"a": 2}),
        id="dict-different-values",
    ),
    pytest.param(
        _PointHolder(point=frozenset({1, 2})),
        _PointHolder(point=frozenset({2, 1})),
        id="other-hashable-leaf",
    ),
]


def _astuple_hash_outcome(value: AbstractValueObject) -> object:
    try:
        return hash(astuple(value))
    except TypeError:
        return TypeError


def _hash_outcome(value: AbstractValueObject) -> object:
    try:
        return hash(value)
    except TypeError:
        return TypeError


@pytest.mark.parametrize(("left", "right"), _PARITY_CASES)
def test_value_object_equality_expect_same_result_as_astuple(
    left: AbstractValueObject, right: AbstractValueObject
) -> None:
    """얕은 비교가 nested dataclass·컬렉션에서도 기존 astuple 비교와 같은 결과를 낸다."""
    assert (left == right) is (astuple(left) == astuple(right))
    assert (right == left) is (astuple(right) == astuple(left))


@pytest.mark.parametrize(("left", "right"), _PARITY_CASES)
def test_value_object_hash_expect_same_hashability_and_consistency(
    left: AbstractValueObject, right: AbstractValueObject
) -> None:
    """hash 가능 여부는 기존 astuple과 같고, 같은 값 객체는 같은 hash를 가진다."""
    for value in (left, right):
        expected = _astuple_hash_outcome(value)
        outcome = _hash_outcome(value)
        assert (outcome is TypeError) is (expected is TypeError)
    if left == right and _hash_outcome(left) is not TypeError:
        assert hash(left) == hash(right)


def test_value_object_compare_and_hash_expect_no_deep_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """비교와 hash가 필드 값을 깊은 복사하지 않는다."""

    def fail_deepcopy(value: object, memo: object = None) -> object:
        raise AssertionError("deepcopy must not run during comparison")

    monkeypatch.setattr(copy, "deepcopy", fail_deepcopy)
    left = _Holder(value=_Money(amount=1, currency="KRW"))
    right = _Holder(value=_Money(amount=1, currency="KRW"))

    assert left == right
    assert hash(left) == hash(right)
