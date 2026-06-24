"""Unit tests for deterministic name-hash field-number assignment.

Mirrors the user scenarios from issue #402: a BaseModel defined without
``ProtoField`` is numbered automatically, adding or reordering fields
never changes an existing field's number, collisions are resolved
deterministically, the protobuf reserved range is avoided, and explicit
``ProtoField`` annotations override the derived number.
"""

from typing import Annotated, Optional

from pydantic import BaseModel
from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.schema.field_number import (
    MAX_FIELD_NUMBER,
    MIN_FIELD_NUMBER,
    RESERVED_RANGE_END,
    RESERVED_RANGE_START,
    _hash_to_number,
    assign_field_numbers,
)


def test_basemodel_without_protofield_gets_numbers_expect_all_fields_numbered() -> None:
    """ProtoField 없는 BaseModel의 모든 필드가 번호를 부여받는지 검증한다 (US-1)."""

    class HelloRequest(BaseModel):
        name: str
        greeting_count: int

    numbers = assign_field_numbers(HelloRequest)

    assert set(numbers) == {"name", "greeting_count"}
    assert all(isinstance(number, int) for number in numbers.values())


def test_same_model_twice_expect_identical_numbers() -> None:
    """동일 모델을 두 번 변환하면 동일 번호가 나오는지 검증한다 (결정론)."""

    class Profile(BaseModel):
        nickname: str
        age: int
        bio: str

    assert assign_field_numbers(Profile) == assign_field_numbers(Profile)


def test_adding_field_expect_existing_field_numbers_unchanged() -> None:
    """필드를 추가해도 기존 필드의 번호가 변하지 않는지 검증한다 (FR-2/SC-1)."""

    class Before(BaseModel):
        name: str
        email: str

    class After(BaseModel):
        name: str
        email: str
        phone: str

    before = assign_field_numbers(Before)
    after = assign_field_numbers(After)

    assert after["name"] == before["name"]
    assert after["email"] == before["email"]
    assert "phone" in after


def test_reordering_fields_expect_existing_field_numbers_unchanged() -> None:
    """필드 선언 순서를 바꿔도 각 필드의 번호가 동일한지 검증한다 (FR-2/SC-1)."""

    class Original(BaseModel):
        first: str
        second: str
        third: str

    class Reordered(BaseModel):
        third: str
        first: str
        second: str

    original = assign_field_numbers(Original)
    reordered = assign_field_numbers(Reordered)

    assert reordered == original


def test_reordering_colliding_pair_expect_identical_numbers() -> None:
    """salt-0 충돌 쌍을 재배치해도 두 필드 번호가 동일한지 검증한다.

    재배치 불변식(SC-1)은 충돌이 있어도 절대적이다 — 할당이 이름 집합의
    순수 함수이기 때문이다. ``f23200``과 ``f3323``은 salt-0 번호가
    동일(78767513)하여 한쪽이 재해싱되지만, 그 결과는 선언 순서와 무관하다.
    """

    class DeclaredAB(BaseModel):
        f3323: str
        f23200: str

    class DeclaredBA(BaseModel):
        f23200: str
        f3323: str

    assert assign_field_numbers(DeclaredAB) == assign_field_numbers(DeclaredBA)


def test_adding_colliding_field_rehashes_the_sorted_loser() -> None:
    """salt-0 충돌 쌍에서 사전순 뒤 이름이 추가 시 재해싱되는 경계를 고정한다.

    자동 번호의 단일 호환성 경계(모듈 docstring "Wire-compatibility
    guarantee and its single boundary")를 명시적으로 박제한다. ``f23200``은
    ``f3323``보다 사전순 앞서므로 salt-0 번호(78767513)를 차지하고, 기존
    필드 ``f3323``은 재해싱된다. 절대 락이 필요하면 ProtoField로 고정한다.
    """

    class Before(BaseModel):
        f3323: str

    class After(BaseModel):
        f3323: str
        f23200: str

    before = assign_field_numbers(Before)
    after = assign_field_numbers(After)

    assert before["f3323"] == _hash_to_number("f3323", 0)
    assert after["f23200"] == _hash_to_number("f3323", 0)
    assert after["f3323"] == _hash_to_number("f3323", 1)
    assert after["f3323"] != before["f3323"]


def test_colliding_field_pinned_with_protofield_is_stable_on_add() -> None:
    """ProtoField로 고정한 필드는 충돌 상대가 추가돼도 번호가 불변임을 검증한다.

    salt-0 충돌 경계에서도 명시 ProtoField는 무조건 그 번호를 유지한다 —
    docstring이 권고하는 "무조건 락" 경로를 검증한다.
    """
    pinned_number = _hash_to_number("f3323", 0)

    class Before(BaseModel):
        f3323: Annotated[str, ProtoField(number=pinned_number)]

    class After(BaseModel):
        f3323: Annotated[str, ProtoField(number=pinned_number)]
        f23200: str

    before = assign_field_numbers(Before)
    after = assign_field_numbers(After)

    assert before["f3323"] == pinned_number
    assert after["f3323"] == pinned_number
    assert after["f23200"] != pinned_number


def test_explicit_protofield_expect_override_number() -> None:
    """ProtoField를 명시하면 해당 번호로 오버라이드되는지 검증한다 (FR-3)."""

    class Mixed(BaseModel):
        name: str
        pinned: Annotated[str, ProtoField(number=7)]

    numbers = assign_field_numbers(Mixed)

    assert numbers["pinned"] == 7


def test_all_explicit_protofields_expect_exact_numbers() -> None:
    """모든 필드에 ProtoField를 명시하면 그 번호가 그대로 사용되는지 검증한다."""

    class Explicit(BaseModel):
        alpha: Annotated[str, ProtoField(number=1)]
        beta: Annotated[int, ProtoField(number=2)]

    numbers = assign_field_numbers(Explicit)

    assert numbers == {"alpha": 1, "beta": 2}


def test_derived_numbers_within_valid_range() -> None:
    """파생 번호가 유효 범위(1~536870911) 안에 있는지 검증한다."""

    class ManyFields(BaseModel):
        a: str
        b: str
        c: str
        d: str
        e: str

    for number in assign_field_numbers(ManyFields).values():
        assert MIN_FIELD_NUMBER <= number <= MAX_FIELD_NUMBER


def test_derived_numbers_avoid_reserved_range() -> None:
    """파생 번호가 예약 범위(19000~19999)를 회피하는지 검증한다."""

    class WideModel(BaseModel):
        f0: str
        f1: str
        f2: str
        f3: str
        f4: str
        f5: str
        f6: str
        f7: str

    for number in assign_field_numbers(WideModel).values():
        assert not RESERVED_RANGE_START <= number <= RESERVED_RANGE_END


def test_hash_landing_in_reserved_range_is_shifted_out() -> None:
    """해시가 예약 범위로 떨어지는 입력이 예약 범위 밖으로 이동되는지 검증한다."""
    candidates = (
        _hash_to_number(f"field_{index}", salt)
        for index in range(50_000)
        for salt in range(2)
    )
    for number in candidates:
        assert not RESERVED_RANGE_START <= number <= RESERVED_RANGE_END
        assert MIN_FIELD_NUMBER <= number <= MAX_FIELD_NUMBER


def test_distinct_derived_fields_expect_distinct_numbers() -> None:
    """서로 다른 필드들이 서로 충돌 없이 고유 번호를 받는지 검증한다."""

    class ManyDistinct(BaseModel):
        alpha: str
        beta: str
        gamma: str
        delta: str

    numbers = assign_field_numbers(ManyDistinct)

    assert len(set(numbers.values())) == len(numbers)


def test_derived_field_colliding_with_explicit_override_expect_rehash() -> None:
    """파생 번호가 명시 ProtoField 번호와 충돌하면 재해싱되는지 검증한다."""
    target = _hash_to_number("auto", 0)

    class Collide(BaseModel):
        auto: str
        pinned: Annotated[int, ProtoField(number=target)]

    numbers = assign_field_numbers(Collide)

    assert numbers["pinned"] == target
    assert numbers["auto"] != target
    assert numbers["auto"] == _hash_to_number("auto", 1)


def test_optional_and_repeated_fields_get_numbers() -> None:
    """optional·repeated 필드도 번호를 부여받는지 검증한다 (타입 매핑 유지)."""

    class Composite(BaseModel):
        tags: list[str]
        nickname: Optional[str] = None  # noqa: UP045 - legacy typing input contract

    numbers = assign_field_numbers(Composite)

    assert set(numbers) == {"tags", "nickname"}
