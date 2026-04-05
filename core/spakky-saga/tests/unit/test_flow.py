"""Unit tests for saga flow types and operator support."""

from spakky.core.common.mutability import immutable
from spakky.saga.models.error_strategy import Compensate, Retry, Skip
from spakky.saga.models.flow import (
    Parallel,
    SagaFlow,
    SagaStep,
    Transaction,
)
from spakky.saga.models.saga_data import AbstractSagaData


@immutable
class _TestSagaData(AbstractSagaData):
    value: int = 0


async def _action(data: _TestSagaData) -> _TestSagaData:
    return data


async def _compensate(data: _TestSagaData) -> None:
    pass


async def _action_b(data: _TestSagaData) -> _TestSagaData:
    return data


async def _compensate_b(data: _TestSagaData) -> None:
    pass


# --- SagaStep tests ---


def test_saga_step_creation() -> None:
    """SagaStep이 action과 기본 on_error로 생성되는지 검증한다."""
    step = SagaStep(action=_action)
    assert step.action is _action
    assert isinstance(step.on_error, Compensate)


def test_saga_step_rshift_creates_transaction() -> None:
    """SagaStep >> compensate가 Transaction을 생성하는지 검증한다."""
    step = SagaStep(action=_action)
    tx = step >> _compensate
    assert isinstance(tx, Transaction)
    assert tx.action is _action
    assert tx.compensate is _compensate


def test_saga_step_and_creates_parallel() -> None:
    """SagaStep & SagaStep이 Parallel을 생성하는지 검증한다."""
    step_a = SagaStep(action=_action)
    step_b = SagaStep(action=_action_b)
    parallel = step_a & step_b
    assert isinstance(parallel, Parallel)
    assert len(parallel.items) == 2
    assert parallel.items[0] is step_a
    assert parallel.items[1] is step_b


def test_saga_step_or_sets_error_strategy() -> None:
    """SagaStep | ErrorStrategy가 on_error를 설정하는지 검증한다."""
    step = SagaStep(action=_action)
    retry = Retry(max_attempts=3)
    step_with_retry = step | retry
    assert isinstance(step_with_retry, SagaStep)
    assert isinstance(step_with_retry.on_error, Retry)
    assert step_with_retry.action is _action


def test_saga_step_or_with_skip() -> None:
    """SagaStep | Skip이 on_error를 Skip으로 설정하는지 검증한다."""
    step = SagaStep(action=_action)
    step_with_skip = step | Skip()
    assert isinstance(step_with_skip.on_error, Skip)


def test_saga_step_rshift_preserves_error_strategy() -> None:
    """SagaStep의 on_error 설정이 >> 연산자 후에도 보존되는지 검증한다."""
    retry = Retry(max_attempts=3)
    step = SagaStep(action=_action, on_error=retry)
    tx = step >> _compensate
    assert isinstance(tx.on_error, Retry)


# --- Transaction tests ---


def test_transaction_creation() -> None:
    """Transaction이 action, compensate, 기본 on_error로 생성되는지 검증한다."""
    tx = Transaction(action=_action, compensate=_compensate)
    assert tx.action is _action
    assert tx.compensate is _compensate
    assert isinstance(tx.on_error, Compensate)


def test_transaction_and_creates_parallel() -> None:
    """Transaction & SagaStep이 Parallel을 생성하는지 검증한다."""
    tx = Transaction(action=_action, compensate=_compensate)
    step = SagaStep(action=_action_b)
    parallel = tx & step
    assert isinstance(parallel, Parallel)
    assert len(parallel.items) == 2
    assert parallel.items[0] is tx
    assert parallel.items[1] is step


def test_transaction_and_transaction_creates_parallel() -> None:
    """Transaction & Transaction이 Parallel을 생성하는지 검증한다."""
    tx_a = Transaction(action=_action, compensate=_compensate)
    tx_b = Transaction(action=_action_b, compensate=_compensate_b)
    parallel = tx_a & tx_b
    assert isinstance(parallel, Parallel)
    assert len(parallel.items) == 2


def test_transaction_or_sets_error_strategy() -> None:
    """Transaction | ErrorStrategy가 on_error를 설정하는지 검증한다."""
    tx = Transaction(action=_action, compensate=_compensate)
    retry = Retry(max_attempts=3)
    tx_with_retry = tx | retry
    assert isinstance(tx_with_retry, Transaction)
    assert isinstance(tx_with_retry.on_error, Retry)
    assert tx_with_retry.action is _action
    assert tx_with_retry.compensate is _compensate


# --- Parallel tests ---


def test_parallel_and_step_extends_group() -> None:
    """Parallel & SagaStep이 기존 그룹에 추가하는지 검증한다."""
    step_a = SagaStep(action=_action)
    step_b = SagaStep(action=_action_b)
    step_c = SagaStep(action=_action)
    parallel = step_a & step_b
    extended = parallel & step_c
    assert isinstance(extended, Parallel)
    assert len(extended.items) == 3


def test_parallel_and_parallel_merges_groups() -> None:
    """Parallel & Parallel이 두 그룹을 병합하는지 검증한다."""
    step_a = SagaStep(action=_action)
    step_b = SagaStep(action=_action_b)
    step_c = SagaStep(action=_action)
    step_d = SagaStep(action=_action_b)
    parallel_1 = step_a & step_b
    parallel_2 = step_c & step_d
    merged = parallel_1 & parallel_2
    assert isinstance(merged, Parallel)
    assert len(merged.items) == 4


def test_saga_step_and_parallel_extends() -> None:
    """SagaStep & Parallel이 SagaStep을 기존 Parallel에 추가하는지 검증한다."""
    step_a = SagaStep(action=_action)
    step_b = SagaStep(action=_action_b)
    step_c = SagaStep(action=_action)
    parallel = step_b & step_c
    extended = step_a & parallel
    assert isinstance(extended, Parallel)
    assert len(extended.items) == 3
    assert extended.items[0] is step_a


def test_transaction_and_parallel_extends() -> None:
    """Transaction & Parallel이 Transaction을 기존 Parallel에 추가하는지 검증한다."""
    tx = Transaction(action=_action, compensate=_compensate)
    step_b = SagaStep(action=_action_b)
    step_c = SagaStep(action=_action)
    parallel = step_b & step_c
    extended = tx & parallel
    assert isinstance(extended, Parallel)
    assert len(extended.items) == 3
    assert extended.items[0] is tx


# --- SagaFlow tests ---


def test_saga_flow_creation_with_steps() -> None:
    """SagaFlow가 여러 FlowItem으로 생성되는지 검증한다."""
    step = SagaStep(action=_action)
    tx = Transaction(action=_action, compensate=_compensate)
    flow = SagaFlow(items=(step, tx))
    assert len(flow.items) == 2
    assert flow.items[0] is step
    assert flow.items[1] is tx


def test_saga_flow_with_callable() -> None:
    """SagaFlow가 Callable을 FlowItem으로 포함할 수 있는지 검증한다."""
    step = SagaStep(action=_action)
    flow = SagaFlow(items=(step, _action))
    assert len(flow.items) == 2
    assert flow.items[1] is _action


def test_saga_flow_with_parallel() -> None:
    """SagaFlow가 Parallel 그룹을 포함할 수 있는지 검증한다."""
    step_a = SagaStep(action=_action)
    step_b = SagaStep(action=_action_b)
    parallel = step_a & step_b
    flow = SagaFlow(items=(parallel,))
    assert len(flow.items) == 1
    assert isinstance(flow.items[0], Parallel)


# --- Operator composition tests ---


def test_combined_rshift_then_or() -> None:
    """(step >> compensate) | Retry 합성이 올바르게 동작하는지 검증한다."""
    step = SagaStep(action=_action)
    tx = step >> _compensate
    tx_with_retry = tx | Retry(max_attempts=3)
    assert isinstance(tx_with_retry, Transaction)
    assert isinstance(tx_with_retry.on_error, Retry)
    assert tx_with_retry.action is _action
    assert tx_with_retry.compensate is _compensate


def test_combined_or_then_rshift() -> None:
    """(step | Retry) >> compensate 합성이 올바르게 동작하는지 검증한다."""
    step = SagaStep(action=_action)
    step_with_retry = step | Retry(max_attempts=3)
    tx = step_with_retry >> _compensate
    assert isinstance(tx, Transaction)
    assert isinstance(tx.on_error, Retry)


def test_combined_rshift_then_and() -> None:
    """(a >> ca) & (b >> cb) 합성이 Parallel을 생성하는지 검증한다."""
    step_a = SagaStep(action=_action)
    step_b = SagaStep(action=_action_b)
    tx_a = step_a >> _compensate
    tx_b = step_b >> _compensate_b
    parallel = tx_a & tx_b
    assert isinstance(parallel, Parallel)
    assert len(parallel.items) == 2
    assert isinstance(parallel.items[0], Transaction)
    assert isinstance(parallel.items[1], Transaction)
