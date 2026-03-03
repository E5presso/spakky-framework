from dataclasses import FrozenInstanceError

import pytest

from spakky.core.common.interfaces.equatable import IEquatable
from spakky.core.common.mutability import immutable, mutable


def test_mutable_is_dataclass() -> None:
    """수정 가능(mutable) 데코레이터가 데이터클래스로 정상 동작함을 검증한다."""

    @mutable
    class MutableDataClass:
        name: str

    MutableDataClass(name="John")
    with pytest.raises(TypeError):
        MutableDataClass("John")  # type: ignore
    with pytest.raises(AssertionError):
        assert MutableDataClass(name="John") == MutableDataClass(name="John")

    @mutable
    class MutableDataClassWithEquatable(MutableDataClass, IEquatable):
        def __eq__(self, __value: object) -> bool:
            if not isinstance(__value, type(self)):
                return False
            return self.name == __value.name

        def __hash__(self) -> int:
            return hash(self.name)

    assert MutableDataClassWithEquatable(name="John") == MutableDataClassWithEquatable(
        name="John"
    )


def test_immutable_is_dataclass() -> None:
    """불변(immutable) 데코레이터가 데이터클래스로 정상 동작하고 수정이 불가능함을 검증한다."""

    @immutable
    class ImmutableDataClass:
        name: str

    ImmutableDataClass(name="John")
    with pytest.raises(TypeError):
        ImmutableDataClass("John")  # type: ignore
    with pytest.raises(AssertionError):
        assert ImmutableDataClass(name="John") == ImmutableDataClass(name="John")
    with pytest.raises(FrozenInstanceError):
        ImmutableDataClass(name="John").name = "Sarah"  # type: ignore

    @immutable
    class ImmutableDataClassWithEquatable(ImmutableDataClass, IEquatable):
        def __eq__(self, __value: object) -> bool:
            if not isinstance(__value, type(self)):
                return False
            return self.name == __value.name

        def __hash__(self) -> int:
            return hash(self.name)

    assert ImmutableDataClassWithEquatable(
        name="John"
    ) == ImmutableDataClassWithEquatable(name="John")
