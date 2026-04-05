"""Unit tests for SagaResult dataclass."""

from dataclasses import FrozenInstanceError

from spakky.core.common.mutability import immutable
from spakky.saga.error import SagaCompensationFailedError
from spakky.saga.models.saga_data import AbstractSagaData
from spakky.saga.models.saga_result import SagaResult, StepRecord
from spakky.saga.models.saga_status import SagaStatus


@immutable
class _TestSagaData(AbstractSagaData):
    order_id: str = "ORD-001"


def test_saga_result_completed_status() -> None:
    """SagaResult가 COMPLETED 상태로 생성 가능한지 검증한다."""
    data = _TestSagaData()
    result = SagaResult(
        status=SagaStatus.COMPLETED,
        data=data,
    )
    assert result.status is SagaStatus.COMPLETED
    assert result.data is data
    assert result.failed_step is None
    assert result.error is None
    assert result.history == ()
    assert result.elapsed == 0.0


def test_saga_result_failed_with_details() -> None:
    """SagaResult가 실패 정보를 포함할 수 있는지 검증한다."""
    data = _TestSagaData()
    error = SagaCompensationFailedError()
    history = (
        StepRecord(name="validate", elapsed=0.1),
        StepRecord(name="create_ticket", elapsed=0.05),
    )
    result = SagaResult(
        status=SagaStatus.FAILED,
        data=data,
        failed_step="create_ticket",
        error=error,
        history=history,
        elapsed=1.5,
    )
    assert result.status is SagaStatus.FAILED
    assert result.failed_step == "create_ticket"
    assert result.error is error
    assert len(result.history) == 2
    assert result.elapsed == 1.5


def test_saga_result_is_immutable() -> None:
    """SagaResult가 불변인지 검증한다."""
    data = _TestSagaData()
    result = SagaResult(status=SagaStatus.COMPLETED, data=data)
    try:
        result.status = SagaStatus.FAILED  # type: ignore
        raise AssertionError("Expected FrozenInstanceError")
    except FrozenInstanceError:
        pass


def test_step_record_creation() -> None:
    """StepRecord가 올바르게 생성되는지 검증한다."""
    record = StepRecord(name="validate_order", elapsed=0.123)
    assert record.name == "validate_order"
    assert record.elapsed == 0.123


def test_step_record_is_immutable() -> None:
    """StepRecord가 불변인지 검증한다."""
    record = StepRecord(name="validate", elapsed=0.1)
    try:
        record.name = "other"  # type: ignore
        raise AssertionError("Expected FrozenInstanceError")
    except FrozenInstanceError:
        pass


def test_saga_result_with_history() -> None:
    """SagaResult가 실행 이력을 포함할 수 있는지 검증한다."""
    data = _TestSagaData()
    history = (
        StepRecord(name="step1", elapsed=0.1),
        StepRecord(name="step2", elapsed=0.2),
        StepRecord(name="step3", elapsed=0.3),
    )
    result = SagaResult(
        status=SagaStatus.COMPLETED,
        data=data,
        history=history,
        elapsed=0.6,
    )
    assert len(result.history) == 3
    assert result.history[0].name == "step1"
    assert result.history[2].elapsed == 0.3


def test_saga_result_timed_out_status() -> None:
    """SagaResult가 TIMED_OUT 상태로 생성 가능한지 검증한다."""
    data = _TestSagaData()
    result = SagaResult(
        status=SagaStatus.TIMED_OUT,
        data=data,
        failed_step="slow_step",
        elapsed=300.0,
    )
    assert result.status is SagaStatus.TIMED_OUT
    assert result.failed_step == "slow_step"
