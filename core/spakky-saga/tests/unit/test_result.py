"""Unit tests for SagaResult and StepRecord."""

from datetime import timedelta
from uuid import UUID

from spakky.core.common.mutability import immutable
from spakky.saga.data import AbstractSagaData
from spakky.saga.result import SagaResult, StepRecord
from spakky.saga.status import SagaStatus


@immutable
class _TestSagaData(AbstractSagaData):
    order_id: UUID


def test_step_record_fields_expect_accessible() -> None:
    """StepRecord의 name과 elapsed 필드에 접근 가능한지 검증한다."""
    record = StepRecord(name="validate", elapsed=timedelta(milliseconds=12))
    assert record.name == "validate"
    assert record.elapsed == timedelta(milliseconds=12)


def test_saga_result_completed_expect_correct_fields() -> None:
    """완료된 SagaResult의 필드를 검증한다."""
    order_id = UUID("12345678-1234-5678-1234-567812345678")
    data = _TestSagaData(order_id=order_id)
    history = (
        StepRecord(name="step1", elapsed=timedelta(milliseconds=10)),
        StepRecord(name="step2", elapsed=timedelta(milliseconds=20)),
    )
    result: SagaResult[_TestSagaData] = SagaResult(
        status=SagaStatus.COMPLETED,
        data=data,
        history=history,
        elapsed=timedelta(milliseconds=30),
    )
    assert result.status is SagaStatus.COMPLETED
    assert result.data is data
    assert result.failed_step is None
    assert result.error is None
    assert len(result.history) == 2
    assert result.elapsed == timedelta(milliseconds=30)


def test_saga_result_failed_expect_error_and_step() -> None:
    """실패한 SagaResult의 failed_step과 error를 검증한다."""
    order_id = UUID("12345678-1234-5678-1234-567812345678")
    data = _TestSagaData(order_id=order_id)
    error = RuntimeError("connection timeout")
    result: SagaResult[_TestSagaData] = SagaResult(
        status=SagaStatus.FAILED,
        data=data,
        failed_step="create_ticket",
        error=error,
    )
    assert result.status is SagaStatus.FAILED
    assert result.failed_step == "create_ticket"
    assert result.error is error


def test_saga_result_defaults_expect_empty_history_and_zero_elapsed() -> None:
    """SagaResult의 기본값이 올바른지 검증한다."""
    order_id = UUID("12345678-1234-5678-1234-567812345678")
    data = _TestSagaData(order_id=order_id)
    result: SagaResult[_TestSagaData] = SagaResult(
        status=SagaStatus.STARTED,
        data=data,
    )
    assert result.history == ()
    assert result.elapsed == timedelta()
    assert result.failed_step is None
    assert result.error is None


def test_saga_result_timed_out_expect_status() -> None:
    """타임아웃된 SagaResult의 상태를 검증한다."""
    order_id = UUID("12345678-1234-5678-1234-567812345678")
    data = _TestSagaData(order_id=order_id)
    result: SagaResult[_TestSagaData] = SagaResult(
        status=SagaStatus.TIMED_OUT,
        data=data,
        failed_step="authorize_payment",
        elapsed=timedelta(minutes=5),
    )
    assert result.status is SagaStatus.TIMED_OUT
    assert result.failed_step == "authorize_payment"
