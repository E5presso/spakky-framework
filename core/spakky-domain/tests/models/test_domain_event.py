from datetime import datetime
from typing import override
from uuid import UUID

import pytest
from spakky.core.common.mutability import immutable

from spakky.domain.error import AbstractDomainValidationError
from spakky.domain.models.event import AbstractDomainEvent


class InvalidEventError(AbstractDomainValidationError):
    """Raised when a test event is invalid."""

    message = "Test event is invalid."


def test_domain_event_validate_called_on_initialization() -> None:
    """도메인 이벤트 초기화 후 override된 validate가 호출됨을 검증한다."""
    validated_codes: list[str] = []

    @immutable
    class ValidatingEvent(AbstractDomainEvent):
        code: str

        @override
        def validate(self) -> None:
            validated_codes.append(self.code)

    event = ValidatingEvent(code="ready")

    assert event.code == "ready"
    assert validated_codes == ["ready"]


def test_domain_event_default_validate_allows_initialization() -> None:
    """validate를 재정의하지 않은 도메인 이벤트 생성이 허용됨을 검증한다."""

    @immutable
    class SampleEvent(AbstractDomainEvent):
        code: str

    event = SampleEvent(code="ready")

    assert event.code == "ready"


def test_domain_event_invalid_state_expect_error() -> None:
    """검증에 실패한 도메인 이벤트 생성이 실패함을 검증한다."""

    @immutable
    class PositiveQuantityEvent(AbstractDomainEvent):
        quantity: int

        @override
        def validate(self) -> None:
            if self.quantity <= 0:
                raise InvalidEventError()

    with pytest.raises(InvalidEventError):
        PositiveQuantityEvent(quantity=0)


def test_domain_event_equals() -> None:
    """동일한 event_id와 timestamp를 가진 도메인 이벤트가 동등함을 검증한다."""

    @immutable
    class SampleEvent(AbstractDomainEvent): ...

    event1: SampleEvent = SampleEvent(
        event_id=UUID("12345678-1234-5678-1234-567812345678"),
        timestamp=datetime.fromisoformat("2024-01-26T11:32:00.000000+09:00"),
    )
    event2: SampleEvent = SampleEvent(
        event_id=UUID("12345678-1234-5678-1234-567812345678"),
        timestamp=datetime.fromisoformat("2024-01-26T11:32:00.000000+09:00"),
    )
    assert event1 == event2


def test_domain_event_not_equals() -> None:
    """다른 timestamp를 가진 도메인 이벤트가 동등하지 않음을 검증한다."""

    @immutable
    class SampleEvent(AbstractDomainEvent): ...

    event1: SampleEvent = SampleEvent(
        event_id=UUID("12345678-1234-5678-1234-567812345678"),
        timestamp=datetime.fromisoformat("2024-01-26T11:32:00.000000+09:00"),
    )
    event2: SampleEvent = SampleEvent(
        event_id=UUID("12345678-1234-5678-1234-567812345678"),
        timestamp=datetime.fromisoformat("2024-01-26T11:31:00.000000+09:00"),
    )
    assert event1 != event2


def test_domain_event_not_equals_with_wrong_type() -> None:
    """다른 타입의 도메인 이벤트가 동등하지 않음을 검증한다."""

    @immutable
    class SampleEvent(AbstractDomainEvent): ...

    @immutable
    class AnotherEvent(AbstractDomainEvent): ...

    event1: SampleEvent = SampleEvent(
        event_id=UUID("12345678-1234-5678-1234-567812345678"),
        timestamp=datetime.fromisoformat("2024-01-26T11:32:00.000000+09:00"),
    )
    event2: AnotherEvent = AnotherEvent(
        event_id=UUID("12345678-1234-5678-1234-567812345678"),
        timestamp=datetime.fromisoformat("2024-01-26T11:32:00.000000+09:00"),
    )
    assert event1 != event2


def test_domain_event_clone() -> None:
    """도메인 이벤트를 복제하면 동등한 객체가 생성됨을 검증한다."""

    @immutable
    class SampleEvent(AbstractDomainEvent): ...

    event1: SampleEvent = SampleEvent(
        event_id=UUID("12345678-1234-5678-1234-567812345678"),
        timestamp=datetime.fromisoformat("2024-01-26T11:32:00.000000+09:00"),
    )
    event2: SampleEvent = event1.clone()
    assert event1 == event2


def test_domain_event_hash() -> None:
    """동일한 도메인 이벤트가 동일한 해시값을 가짐을 검증한다."""

    @immutable
    class SampleEvent(AbstractDomainEvent): ...

    event1: SampleEvent = SampleEvent(
        event_id=UUID("12345678-1234-5678-1234-567812345678"),
        timestamp=datetime.fromisoformat("2024-01-26T11:32:00.000000+09:00"),
    )
    event2: SampleEvent = SampleEvent(
        event_id=UUID("12345678-1234-5678-1234-567812345678"),
        timestamp=datetime.fromisoformat("2024-01-26T11:32:00.000000+09:00"),
    )
    assert hash(event1) == hash(event2)


def test_domain_event_hash_different_values() -> None:
    """다른 event_id나 timestamp를 가진 이벤트가 다른 해시값을 가짐을 검증한다."""

    @immutable
    class SampleEvent(AbstractDomainEvent): ...

    event1: SampleEvent = SampleEvent(
        event_id=UUID("12345678-1234-5678-1234-567812345678"),
        timestamp=datetime.fromisoformat("2024-01-26T11:32:00.000000+09:00"),
    )
    event2: SampleEvent = SampleEvent(
        event_id=UUID("87654321-4321-8765-4321-876543218765"),
        timestamp=datetime.fromisoformat("2024-01-26T11:32:00.000000+09:00"),
    )
    event3: SampleEvent = SampleEvent(
        event_id=UUID("12345678-1234-5678-1234-567812345678"),
        timestamp=datetime.fromisoformat("2024-01-26T11:33:00.000000+09:00"),
    )

    # Different event_id should produce different hash
    assert hash(event1) != hash(event2)
    # Different timestamp should produce different hash
    assert hash(event1) != hash(event3)


def test_domain_event_hash_in_set() -> None:
    """도메인 이벤트가 set의 요소로 올바르게 동작함을 검증한다."""

    @immutable
    class SampleEvent(AbstractDomainEvent): ...

    event1: SampleEvent = SampleEvent(
        event_id=UUID("12345678-1234-5678-1234-567812345678"),
        timestamp=datetime.fromisoformat("2024-01-26T11:32:00.000000+09:00"),
    )
    event2: SampleEvent = SampleEvent(
        event_id=UUID("12345678-1234-5678-1234-567812345678"),
        timestamp=datetime.fromisoformat("2024-01-26T11:32:00.000000+09:00"),
    )
    event3: SampleEvent = SampleEvent(
        event_id=UUID("87654321-4321-8765-4321-876543218765"),
        timestamp=datetime.fromisoformat("2024-01-26T11:32:00.000000+09:00"),
    )

    events = {event1, event2, event3}

    # event1 and event2 are equal, so set should contain only 2 elements
    assert len(events) == 2
    assert event1 in events
    assert event2 in events
    assert event3 in events


def test_domain_event_compare() -> None:
    """도메인 이벤트가 timestamp 기준으로 정렬 가능함을 검증한다."""

    @immutable
    class SampleEvent(AbstractDomainEvent): ...

    events: list[SampleEvent] = [
        SampleEvent(
            event_id=UUID("12345678-1234-5678-1234-567812345678"),
            timestamp=datetime.fromisoformat("2024-01-01T00:00:30.000000+09:00"),
        ),
        SampleEvent(
            event_id=UUID("12345678-1234-5678-1234-567812345678"),
            timestamp=datetime.fromisoformat("2024-01-01T00:01:00.000000+09:00"),
        ),
        SampleEvent(
            event_id=UUID("12345678-1234-5678-1234-567812345678"),
            timestamp=datetime.fromisoformat("2024-01-01T00:00:40.000000+09:00"),
        ),
        SampleEvent(
            event_id=UUID("12345678-1234-5678-1234-567812345678"),
            timestamp=datetime.fromisoformat("2024-01-01T00:00:50.000000+09:00"),
        ),
        SampleEvent(
            event_id=UUID("12345678-1234-5678-1234-567812345678"),
            timestamp=datetime.fromisoformat("2024-01-01T00:00:20.000000+09:00"),
        ),
        SampleEvent(
            event_id=UUID("12345678-1234-5678-1234-567812345678"),
            timestamp=datetime.fromisoformat("2024-01-01T00:00:10.000000+09:00"),
        ),
    ]
    events.sort()
    assert events == [
        SampleEvent(
            event_id=UUID("12345678-1234-5678-1234-567812345678"),
            timestamp=datetime.fromisoformat("2024-01-01T00:00:10.000000+09:00"),
        ),
        SampleEvent(
            event_id=UUID("12345678-1234-5678-1234-567812345678"),
            timestamp=datetime.fromisoformat("2024-01-01T00:00:20.000000+09:00"),
        ),
        SampleEvent(
            event_id=UUID("12345678-1234-5678-1234-567812345678"),
            timestamp=datetime.fromisoformat("2024-01-01T00:00:30.000000+09:00"),
        ),
        SampleEvent(
            event_id=UUID("12345678-1234-5678-1234-567812345678"),
            timestamp=datetime.fromisoformat("2024-01-01T00:00:40.000000+09:00"),
        ),
        SampleEvent(
            event_id=UUID("12345678-1234-5678-1234-567812345678"),
            timestamp=datetime.fromisoformat("2024-01-01T00:00:50.000000+09:00"),
        ),
        SampleEvent(
            event_id=UUID("12345678-1234-5678-1234-567812345678"),
            timestamp=datetime.fromisoformat("2024-01-01T00:01:00.000000+09:00"),
        ),
    ]

    assert SampleEvent(
        timestamp=datetime.fromisoformat("2024-01-01T00:00:10.000000+09:00")
    ) < SampleEvent(
        timestamp=datetime.fromisoformat("2024-01-01T00:00:20.000000+09:00")
    )
    assert SampleEvent(
        timestamp=datetime.fromisoformat("2024-01-01T00:00:10.000000+09:00")
    ) <= SampleEvent(
        timestamp=datetime.fromisoformat("2024-01-01T00:00:20.000000+09:00")
    )
    assert SampleEvent(
        timestamp=datetime.fromisoformat("2024-01-01T00:00:20.000000+09:00")
    ) > SampleEvent(
        timestamp=datetime.fromisoformat("2024-01-01T00:00:10.000000+09:00")
    )
    assert SampleEvent(
        timestamp=datetime.fromisoformat("2024-01-01T00:00:20.000000+09:00")
    ) >= SampleEvent(
        timestamp=datetime.fromisoformat("2024-01-01T00:00:10.000000+09:00")
    )


def test_domain_event_name() -> None:
    """도메인 이벤트의 event_name 속성이 클래스명을 반환함을 검증한다."""

    @immutable
    class SampleEvent(AbstractDomainEvent): ...

    event: SampleEvent = SampleEvent(
        event_id=UUID("12345678-1234-5678-1234-567812345678"),
        timestamp=datetime.fromisoformat("2024-01-26T11:32:00.000000+09:00"),
    )
    assert event.event_name == "SampleEvent"
