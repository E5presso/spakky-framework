"""Unit tests for deterministic name-hash field-number assignment.

Mirrors the user scenarios from issue #402: a BaseModel defined without
``ProtoField`` is numbered automatically, adding or reordering fields
never changes an existing field's number, collisions are resolved
deterministically, the protobuf reserved range is avoided, and explicit
``ProtoField`` annotations override the derived number.
"""

from typing import Annotated, Optional

import pytest
from pydantic import BaseModel
from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.error import (
    DuplicateProtoFieldNumberError,
    InvalidProtoFieldNumberError,
    ProtoFieldNumberConflictError,
)
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


def test_explicit_number_colliding_with_auto_primary_raises_conflict() -> None:
    """명시 번호가 자동 필드의 salt-0 번호와 충돌하면 빌드 오류로 막는지 검증한다.

    자동 ``name`` 필드의 salt-0 번호를 새 ProtoField가 명시하면, 조용히
    ``name``을 재번호화하는 대신 ProtoFieldNumberConflictError를 던져 작성자가
    충돌을 명시적으로 해소하게 한다 (silent wire 번호 변경 차단).
    """
    auto_number = _hash_to_number("name", 0)

    class Conflicting(BaseModel):
        name: str
        pinned: Annotated[str, ProtoField(number=auto_number)]

    with pytest.raises(ProtoFieldNumberConflictError) as exc_info:
        assign_field_numbers(Conflicting)

    assert exc_info.value.derived_field_name == "name"
    assert exc_info.value.explicit_field_name == "pinned"
    assert exc_info.value.number == auto_number


def test_explicit_number_not_colliding_with_auto_primary_is_stable() -> None:
    """명시 번호가 자동 필드와 충돌하지 않으면 두 필드가 모두 유지되는지 검증한다.

    docstring이 권고하는 "ProtoField로 번호 고정" 경로의 정상 케이스다 —
    명시 번호가 자동 필드의 salt-0 번호와 다르면 충돌 없이 공존한다.
    """

    class Mixed(BaseModel):
        name: str
        pinned: Annotated[str, ProtoField(number=1)]

    numbers = assign_field_numbers(Mixed)

    assert numbers["pinned"] == 1
    assert numbers["name"] == _hash_to_number("name", 0)


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


def test_optional_and_repeated_fields_get_numbers() -> None:
    """optional·repeated 필드도 번호를 부여받는지 검증한다 (타입 매핑 유지)."""

    class Composite(BaseModel):
        tags: list[str]
        nickname: Optional[str] = None  # noqa: UP045 - legacy typing input contract

    numbers = assign_field_numbers(Composite)

    assert set(numbers) == {"tags", "nickname"}


def test_explicit_number_in_reserved_range_raises_invalid() -> None:
    """예약 범위(19000~19999)를 명시한 ProtoField가 빌드 오류로 차단되는지 검증한다.

    자동 경로는 예약 범위를 회피하지만 명시 override는 그 회피를 우회한다.
    예약 범위 번호를 명시하면 descriptor pool 빌드 시점이 아니라 번호 부여
    시점에 InvalidProtoFieldNumberError로 조기 차단되어야 한다 (US: 사용자가
    실수로 19000번대를 지정한 경우).
    """

    class Reserved(BaseModel):
        name: Annotated[str, ProtoField(number=RESERVED_RANGE_START)]

    with pytest.raises(InvalidProtoFieldNumberError) as exc_info:
        assign_field_numbers(Reserved)

    assert exc_info.value.field_name == "name"
    assert exc_info.value.number == RESERVED_RANGE_START
    assert exc_info.value.model_type is Reserved


def test_explicit_number_at_reserved_range_end_raises_invalid() -> None:
    """예약 범위 끝(19999)을 명시한 ProtoField도 차단되는지 경계값을 고정한다."""

    class ReservedEnd(BaseModel):
        name: Annotated[str, ProtoField(number=RESERVED_RANGE_END)]

    with pytest.raises(InvalidProtoFieldNumberError) as exc_info:
        assign_field_numbers(ReservedEnd)

    assert exc_info.value.number == RESERVED_RANGE_END


def test_explicit_number_above_max_raises_invalid() -> None:
    """유효 범위 상한(536870911)을 초과한 명시 번호가 차단되는지 검증한다.

    사용자가 2**29 이상 번호를 명시하면 protobuf가 거부하기 전에
    InvalidProtoFieldNumberError로 조기 실패해야 한다.
    """

    class TooBig(BaseModel):
        name: Annotated[str, ProtoField(number=MAX_FIELD_NUMBER + 1)]

    with pytest.raises(InvalidProtoFieldNumberError) as exc_info:
        assign_field_numbers(TooBig)

    assert exc_info.value.field_name == "name"
    assert exc_info.value.number == MAX_FIELD_NUMBER + 1


def test_explicit_number_below_min_raises_invalid() -> None:
    """유효 범위 하한(1) 미만(0)을 명시한 번호가 차단되는지 검증한다.

    0이나 음수는 유효한 protobuf 필드 번호가 아니다 — 번호 부여 시점에
    InvalidProtoFieldNumberError로 막아야 한다.
    """

    class TooSmall(BaseModel):
        name: Annotated[str, ProtoField(number=MIN_FIELD_NUMBER - 1)]

    with pytest.raises(InvalidProtoFieldNumberError) as exc_info:
        assign_field_numbers(TooSmall)

    assert exc_info.value.number == MIN_FIELD_NUMBER - 1


def test_duplicate_explicit_numbers_raises_duplicate() -> None:
    """같은 메시지 내 두 명시 ProtoField 번호가 중복이면 차단되는지 검증한다.

    한 메시지에서 두 필드가 동일한 ProtoField(number=N)를 가지면 descriptor
    pool이 거부하기 전에 DuplicateProtoFieldNumberError로 조기 실패하여 두
    충돌 필드와 공유 번호를 알려야 한다 (US: 복붙 실수로 같은 번호 명시).
    """

    class Duplicated(BaseModel):
        first: Annotated[str, ProtoField(number=5)]
        second: Annotated[str, ProtoField(number=5)]

    with pytest.raises(DuplicateProtoFieldNumberError) as exc_info:
        assign_field_numbers(Duplicated)

    assert exc_info.value.first_field_name == "first"
    assert exc_info.value.second_field_name == "second"
    assert exc_info.value.number == 5
    assert exc_info.value.model_type is Duplicated


def test_distinct_explicit_numbers_are_accepted() -> None:
    """서로 다른 명시 번호를 가진 두 필드는 정상적으로 공존하는지 검증한다.

    유효·고유한 명시 번호는 검증을 통과해 그대로 부여되는 정상 경로다 —
    중복 검증이 정상 케이스를 막지 않음을 보장한다.
    """

    class DistinctExplicit(BaseModel):
        first: Annotated[str, ProtoField(number=5)]
        second: Annotated[str, ProtoField(number=6)]

    numbers = assign_field_numbers(DistinctExplicit)

    assert numbers == {"first": 5, "second": 6}
