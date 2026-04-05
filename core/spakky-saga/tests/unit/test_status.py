"""Unit tests for SagaStatus enum."""

from spakky.saga.status import SagaStatus


def test_saga_status_member_count_expect_six() -> None:
    """SagaStatus가 정확히 6개의 멤버를 가지는지 검증한다."""
    assert len(SagaStatus) == 6


def test_saga_status_started_expect_correct_value() -> None:
    """STARTED 상태의 값을 검증한다."""
    assert SagaStatus.STARTED.value == "STARTED"


def test_saga_status_running_expect_correct_value() -> None:
    """RUNNING 상태의 값을 검증한다."""
    assert SagaStatus.RUNNING.value == "RUNNING"


def test_saga_status_compensating_expect_correct_value() -> None:
    """COMPENSATING 상태의 값을 검증한다."""
    assert SagaStatus.COMPENSATING.value == "COMPENSATING"


def test_saga_status_completed_expect_correct_value() -> None:
    """COMPLETED 상태의 값을 검증한다."""
    assert SagaStatus.COMPLETED.value == "COMPLETED"


def test_saga_status_failed_expect_correct_value() -> None:
    """FAILED 상태의 값을 검증한다."""
    assert SagaStatus.FAILED.value == "FAILED"


def test_saga_status_timed_out_expect_correct_value() -> None:
    """TIMED_OUT 상태의 값을 검증한다."""
    assert SagaStatus.TIMED_OUT.value == "TIMED_OUT"
