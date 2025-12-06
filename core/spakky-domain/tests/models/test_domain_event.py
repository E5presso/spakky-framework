from datetime import datetime
from uuid import UUID

from spakky.core.common.mutability import immutable

from spakky.domain.models.event import AbstractDomainEvent


def test_domain_event_equals() -> None:
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
    @immutable
    class SampleEvent(AbstractDomainEvent): ...

    event1: SampleEvent = SampleEvent(
        event_id=UUID("12345678-1234-5678-1234-567812345678"),
        timestamp=datetime.fromisoformat("2024-01-26T11:32:00.000000+09:00"),
    )
    event2: SampleEvent = event1.clone()
    assert event1 == event2


def test_domain_event_hash() -> None:
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
    """Test that events with different id/timestamp have different hashes."""

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
    """Test that events work correctly as set elements."""

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
    @immutable
    class SampleEvent(AbstractDomainEvent): ...

    event: SampleEvent = SampleEvent(
        event_id=UUID("12345678-1234-5678-1234-567812345678"),
        timestamp=datetime.fromisoformat("2024-01-26T11:32:00.000000+09:00"),
    )
    assert event.event_name == "SampleEvent"
