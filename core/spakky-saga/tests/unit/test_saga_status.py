"""Unit tests for SagaStatus enum."""

from enum import Enum

from spakky.saga.models.saga_status import SagaStatus


def test_saga_status_is_enum() -> None:
    """SagaStatus가 Enum 서브클래스인지 검증한다."""
    assert issubclass(SagaStatus, Enum)


def test_saga_status_has_six_members() -> None:
    """SagaStatus가 정확히 6개의 멤버를 가지는지 검증한다."""
    assert len(SagaStatus) == 6


def test_saga_status_started() -> None:
    """SagaStatus.STARTED가 올바른 값을 가지는지 검증한다."""
    assert SagaStatus.STARTED.value == "STARTED"


def test_saga_status_running() -> None:
    """SagaStatus.RUNNING이 올바른 값을 가지는지 검증한다."""
    assert SagaStatus.RUNNING.value == "RUNNING"


def test_saga_status_compensating() -> None:
    """SagaStatus.COMPENSATING이 올바른 값을 가지는지 검증한다."""
    assert SagaStatus.COMPENSATING.value == "COMPENSATING"


def test_saga_status_completed() -> None:
    """SagaStatus.COMPLETED가 올바른 값을 가지는지 검증한다."""
    assert SagaStatus.COMPLETED.value == "COMPLETED"


def test_saga_status_failed() -> None:
    """SagaStatus.FAILED가 올바른 값을 가지는지 검증한다."""
    assert SagaStatus.FAILED.value == "FAILED"


def test_saga_status_timed_out() -> None:
    """SagaStatus.TIMED_OUT이 올바른 값을 가지는지 검증한다."""
    assert SagaStatus.TIMED_OUT.value == "TIMED_OUT"


def test_saga_status_members_match_expected_names() -> None:
    """SagaStatus 멤버 이름이 기대값과 일치하는지 검증한다."""
    expected = {
        "STARTED",
        "RUNNING",
        "COMPENSATING",
        "COMPLETED",
        "FAILED",
        "TIMED_OUT",
    }
    assert {s.name for s in SagaStatus} == expected
