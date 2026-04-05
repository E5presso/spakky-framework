"""Unit tests for saga flow composition types."""

from datetime import timedelta
from uuid import UUID

from spakky.core.common.mutability import immutable
from spakky.saga.data import AbstractSagaData
from spakky.saga.flow import Parallel, SagaFlow, SagaStep, Transaction
from spakky.saga.strategy import Compensate, Retry, Skip


@immutable
class _TestData(AbstractSagaData):
    order_id: UUID


async def _action(data: _TestData) -> _TestData:
    return data


async def _compensate(data: _TestData) -> None:
    pass


async def _action2(data: _TestData) -> _TestData:
    return data


async def _compensate2(data: _TestData) -> None:
    pass


# --- SagaStep ---


def test_saga_step_creation_expect_default_on_error() -> None:
    """SagaStep 생성 시 기본 on_error가 Compensate인지 검증한다."""
    step = SagaStep(action=_action)
    assert step.action is _action
    assert isinstance(step.on_error, Compensate)


def test_saga_step_rshift_expect_transaction() -> None:
    """SagaStep >> compensate가 Transaction을 반환하는지 검증한다."""
    step = SagaStep(action=_action)
    txn = step >> _compensate
    assert isinstance(txn, Transaction)
    assert txn.action is _action
    assert txn.compensate is _compensate
    assert isinstance(txn.on_error, Compensate)


def test_saga_step_and_step_expect_parallel() -> None:
    """SagaStep & SagaStep이 Parallel을 반환하는지 검증한다."""
    step1 = SagaStep(action=_action)
    step2 = SagaStep(action=_action2)
    par = step1 & step2
    assert isinstance(par, Parallel)
    assert len(par.items) == 2
    assert par.items[0] is step1
    assert par.items[1] is step2


def test_saga_step_or_strategy_expect_new_step_with_strategy() -> None:
    """SagaStep | strategy가 on_error가 변경된 새 SagaStep을 반환하는지 검증한다."""
    step = SagaStep(action=_action)
    step_with_skip = step | Skip()
    assert isinstance(step_with_skip, SagaStep)
    assert isinstance(step_with_skip.on_error, Skip)
    assert step_with_skip.action is _action


def test_saga_step_or_retry_expect_retry_strategy() -> None:
    """SagaStep | Retry가 Retry 전략을 설정하는지 검증한다."""
    step = SagaStep(action=_action)
    step_with_retry = step | Retry(max_attempts=5)
    assert isinstance(step_with_retry.on_error, Retry)
    assert step_with_retry.on_error.max_attempts == 5


def test_saga_step_rshift_preserves_on_error_expect_strategy_in_transaction() -> None:
    """SagaStep의 on_error가 >> 연산 시 Transaction에 전달되는지 검증한다."""
    step = SagaStep(action=_action, on_error=Retry(max_attempts=3))
    txn = step >> _compensate
    assert isinstance(txn.on_error, Retry)


def test_saga_step_default_timeout_expect_none() -> None:
    """SagaStep 생성 시 기본 timeout이 None인지 검증한다."""
    step = SagaStep(action=_action)
    assert step.timeout is None


def test_saga_step_with_timeout_expect_preserved() -> None:
    """SagaStep에 timeout을 설정하면 값이 보존되는지 검증한다."""
    step = SagaStep(action=_action, timeout=timedelta(seconds=30))
    assert step.timeout == timedelta(seconds=30)


def test_saga_step_rshift_preserves_timeout_expect_timeout_in_transaction() -> None:
    """SagaStep의 timeout이 >> 연산 시 Transaction에 전달되는지 검증한다."""
    step = SagaStep(action=_action, timeout=timedelta(seconds=10))
    txn = step >> _compensate
    assert txn.timeout == timedelta(seconds=10)


def test_saga_step_or_preserves_timeout_expect_timeout_kept() -> None:
    """SagaStep | strategy가 timeout을 보존하는지 검증한다."""
    step = SagaStep(action=_action, timeout=timedelta(seconds=5))
    step_with_skip = step | Skip()
    assert step_with_skip.timeout == timedelta(seconds=5)


def test_transaction_default_timeout_expect_none() -> None:
    """Transaction 생성 시 기본 timeout이 None인지 검증한다."""
    txn = Transaction(action=_action, compensate=_compensate)
    assert txn.timeout is None


def test_transaction_with_timeout_expect_preserved() -> None:
    """Transaction에 timeout을 설정하면 값이 보존되는지 검증한다."""
    txn = Transaction(
        action=_action, compensate=_compensate, timeout=timedelta(seconds=15)
    )
    assert txn.timeout == timedelta(seconds=15)


def test_transaction_or_preserves_timeout_expect_timeout_kept() -> None:
    """Transaction | strategy가 timeout을 보존하는지 검증한다."""
    txn = Transaction(
        action=_action, compensate=_compensate, timeout=timedelta(seconds=20)
    )
    txn_with_retry = txn | Retry(max_attempts=2)
    assert txn_with_retry.timeout == timedelta(seconds=20)


# --- Transaction ---


def test_transaction_creation_expect_correct_fields() -> None:
    """Transaction 생성을 검증한다."""
    txn = Transaction(action=_action, compensate=_compensate)
    assert txn.action is _action
    assert txn.compensate is _compensate
    assert isinstance(txn.on_error, Compensate)


def test_transaction_and_step_expect_parallel() -> None:
    """Transaction & SagaStep이 Parallel을 반환하는지 검증한다."""
    txn = Transaction(action=_action, compensate=_compensate)
    step = SagaStep(action=_action2)
    par = txn & step
    assert isinstance(par, Parallel)
    assert len(par.items) == 2
    assert par.items[0] is txn
    assert par.items[1] is step


def test_transaction_and_transaction_expect_parallel() -> None:
    """Transaction & Transaction이 Parallel을 반환하는지 검증한다."""
    txn1 = Transaction(action=_action, compensate=_compensate)
    txn2 = Transaction(action=_action2, compensate=_compensate2)
    par = txn1 & txn2
    assert isinstance(par, Parallel)
    assert len(par.items) == 2


def test_transaction_or_strategy_expect_new_transaction() -> None:
    """Transaction | strategy가 on_error가 변경된 새 Transaction을 반환하는지 검증한다."""
    txn = Transaction(action=_action, compensate=_compensate)
    txn_with_retry = txn | Retry(max_attempts=2, then=Skip())
    assert isinstance(txn_with_retry, Transaction)
    assert isinstance(txn_with_retry.on_error, Retry)
    assert txn_with_retry.on_error.max_attempts == 2
    assert txn_with_retry.action is _action
    assert txn_with_retry.compensate is _compensate


# --- Parallel ---


def test_parallel_creation_expect_items() -> None:
    """Parallel 생성을 검증한다."""
    step1 = SagaStep(action=_action)
    step2 = SagaStep(action=_action2)
    par = Parallel(items=(step1, step2))
    assert len(par.items) == 2


def test_parallel_and_step_expect_extended_parallel() -> None:
    """Parallel & SagaStep이 확장된 Parallel을 반환하는지 검증한다."""
    step1 = SagaStep(action=_action)
    step2 = SagaStep(action=_action2)
    par = Parallel(items=(step1,))
    par_extended = par & step2
    assert isinstance(par_extended, Parallel)
    assert len(par_extended.items) == 2
    assert par_extended.items[0] is step1
    assert par_extended.items[1] is step2


def test_parallel_and_parallel_expect_merged_parallel() -> None:
    """Parallel & Parallel이 병합된 Parallel을 반환하는지 검증한다."""
    step1 = SagaStep(action=_action)
    step2 = SagaStep(action=_action2)
    par1 = Parallel(items=(step1,))
    par2 = Parallel(items=(step2,))
    merged = par1 & par2
    assert isinstance(merged, Parallel)
    assert len(merged.items) == 2
    assert merged.items[0] is step1
    assert merged.items[1] is step2


def test_step_and_parallel_expect_prepended() -> None:
    """SagaStep & Parallel이 step을 앞에 추가하는지 검증한다."""
    step1 = SagaStep(action=_action)
    step2 = SagaStep(action=_action2)
    par = Parallel(items=(step2,))
    result = step1 & par
    assert isinstance(result, Parallel)
    assert len(result.items) == 2
    assert result.items[0] is step1
    assert result.items[1] is step2


def test_transaction_and_parallel_expect_prepended() -> None:
    """Transaction & Parallel이 transaction을 앞에 추가하는지 검증한다."""
    txn = Transaction(action=_action, compensate=_compensate)
    step = SagaStep(action=_action2)
    par = Parallel(items=(step,))
    result = txn & par
    assert isinstance(result, Parallel)
    assert len(result.items) == 2
    assert result.items[0] is txn
    assert result.items[1] is step


# --- SagaFlow ---


def test_saga_flow_creation_expect_items() -> None:
    """SagaFlow 생성을 검증한다."""
    step1 = SagaStep(action=_action)
    step2 = SagaStep(action=_action2)
    flow = SagaFlow(items=(step1, step2))
    assert len(flow.items) == 2
    assert flow.saga_timeout is None
    assert flow.compensation_failure_handler is None


def test_saga_flow_timeout_expect_new_flow_with_timeout() -> None:
    """SagaFlow.timeout()이 새 SagaFlow를 반환하는지 검증한다."""
    step = SagaStep(action=_action)
    flow = SagaFlow(items=(step,))
    flow_with_timeout = flow.timeout(timedelta(minutes=5))
    assert isinstance(flow_with_timeout, SagaFlow)
    assert flow_with_timeout.saga_timeout == timedelta(minutes=5)
    assert flow.saga_timeout is None  # 원본 변경 없음


def test_saga_flow_on_compensation_failure_expect_handler_set() -> None:
    """SagaFlow.on_compensation_failure()가 핸들러를 설정하는지 검증한다."""
    step = SagaStep(action=_action)
    flow = SagaFlow(items=(step,))
    flow_with_handler = flow.on_compensation_failure(_compensate)
    assert flow_with_handler.compensation_failure_handler is _compensate
    assert flow.compensation_failure_handler is None  # 원본 변경 없음


def test_saga_flow_chained_config_expect_both_set() -> None:
    """SagaFlow 설정 메서드를 체이닝할 수 있는지 검증한다."""
    step = SagaStep(action=_action)
    flow = (
        SagaFlow(items=(step,))
        .timeout(timedelta(minutes=5))
        .on_compensation_failure(_compensate)
    )
    assert flow.saga_timeout == timedelta(minutes=5)
    assert flow.compensation_failure_handler is _compensate


# --- Operator composition ---


def test_rshift_then_or_expect_transaction_with_strategy() -> None:
    """(step >> compensate) | strategy 조합을 검증한다."""
    step = SagaStep(action=_action)
    txn = (step >> _compensate) | Retry(max_attempts=3)
    assert isinstance(txn, Transaction)
    assert isinstance(txn.on_error, Retry)


def test_step_or_then_rshift_expect_transaction_preserves_strategy() -> None:
    """(step | strategy) >> compensate 조합을 검증한다."""
    step = SagaStep(action=_action)
    txn = (step | Retry(max_attempts=3)) >> _compensate
    assert isinstance(txn, Transaction)
    assert isinstance(txn.on_error, Retry)


def test_three_way_and_expect_parallel_with_three_items() -> None:
    """a & b & c가 3개 아이템의 Parallel을 만드는지 검증한다."""
    step1 = SagaStep(action=_action)
    step2 = SagaStep(action=_action2)
    step3 = SagaStep(action=_action)
    par = step1 & step2 & step3
    assert isinstance(par, Parallel)
    assert len(par.items) == 3
