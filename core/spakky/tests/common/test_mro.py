from typing import Generic, Protocol, TypeVar

import pytest

from spakky.core.common.error import GenericMROTypeError
from spakky.core.common.mro import generic_mro, is_family_with


def test_generic_mro_normal_inheritance() -> None:
    """일반 클래스 상속 구조에서 MRO(Method Resolution Order)를 정확히 계산함을 검증한다."""

    class A: ...

    class B(A): ...

    class C: ...

    class D: ...

    class E(B): ...

    class F(C): ...

    class G(D, E, F): ...

    class H(E, F): ...

    class I(G): ...  # noqa: E742

    class J: ...

    class K(G): ...

    class L(H): ...

    class M(I): ...

    class N(J, K): ...

    class O(L): ...  # noqa: E742

    assert generic_mro(M) == [M, I, G, D, E, B, A, F, C, object]
    assert generic_mro(N) == [N, J, K, G, D, E, B, A, F, C, object]
    assert generic_mro(O) == [O, L, H, E, B, A, F, C, object]


def test_generic_mro_with_generic_inheritance() -> None:
    """제네릭 타입을 포함한 상속 구조에서 MRO를 정확히 계산함을 검증한다."""
    T_co = TypeVar("T_co", covariant=True)

    class A: ...

    class B(A): ...

    class IC(Protocol, Generic[T_co]): ...

    class D: ...

    class E(B): ...

    class F(IC[T_co], Generic[T_co]): ...

    class G(D, E, F[int]): ...

    class H(E, F[str]): ...

    class I(G): ...  # noqa: E742

    class J: ...

    class K(G): ...

    class L(H): ...

    class M(I): ...

    class N(J, K): ...

    class O(L): ...  # noqa: E742

    assert generic_mro(M) == [
        M,
        I,
        G,
        D,
        E,
        B,
        A,
        F[int],
        IC[int],
        Protocol,
        Generic,
        object,
    ]
    assert generic_mro(N) == [
        N,
        J,
        K,
        G,
        D,
        E,
        B,
        A,
        F[int],
        IC[int],
        Protocol,
        Generic,
        object,
    ]
    assert generic_mro(O) == [
        O,
        L,
        H,
        E,
        B,
        A,
        F[str],
        IC[str],
        Protocol,
        Generic,
        object,
    ]


def test_generic_mro_with_non_class_object() -> None:
    """클래스가 아닌 객체에 대해 generic_mro 호출 시 GenericMROTypeError가 발생함을 검증한다."""

    def a(x: int) -> int:
        return x

    with pytest.raises(GenericMROTypeError):
        generic_mro(a)


def test_is_family_with_parent_class_expect_true() -> None:
    """is_family_with가 부모 클래스를 MRO에서 찾으면 True를 반환함을 검증한다."""

    class Parent: ...

    class Child(Parent): ...

    assert is_family_with(Child, Parent) is True


def test_is_family_with_unrelated_class_expect_false() -> None:
    """is_family_with가 관련 없는 클래스에 대해 False를 반환함을 검증한다."""

    class A: ...

    class B: ...

    assert is_family_with(A, B) is False
