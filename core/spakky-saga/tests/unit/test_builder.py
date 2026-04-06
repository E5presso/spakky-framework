"""Unit tests for saga flow builder functions."""

from datetime import timedelta
from uuid import UUID

import pytest

from spakky.core.common.mutability import immutable
from spakky.saga.data import AbstractSagaData
from spakky.saga.error import SagaFlowDefinitionError
from spakky.saga.flow import (
    Parallel,
    SagaFlow,
    SagaStep,
    Transaction,
    parallel,
    saga_flow,
    step,
)
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


# --- step() ---


def test_step_action_only_expect_saga_step() -> None:
    """step(action)이 SagaStep을 반환하는지 검증한다."""
    result = step(_action)
    assert isinstance(result, SagaStep)
    assert result.action is _action
    assert isinstance(result.on_error, Compensate)
    assert result.timeout is None


def test_step_with_compensate_expect_transaction() -> None:
    """step(action, compensate=)이 Transaction을 반환하는지 검증한다."""
    result = step(_action, compensate=_compensate)
    assert isinstance(result, Transaction)
    assert result.action is _action
    assert result.compensate is _compensate
    assert isinstance(result.on_error, Compensate)


def test_step_with_on_error_expect_strategy_applied() -> None:
    """step(action, on_error=)이 에러 전략을 적용하는지 검증한다."""
    result = step(_action, on_error=Skip())
    assert isinstance(result, SagaStep)
    assert isinstance(result.on_error, Skip)


def test_step_with_compensate_and_on_error_expect_transaction_with_strategy() -> None:
    """step(action, compensate=, on_error=)이 Transaction에 전략을 적용하는지 검증한다."""
    result = step(_action, compensate=_compensate, on_error=Retry(max_attempts=3))
    assert isinstance(result, Transaction)
    assert isinstance(result.on_error, Retry)
    assert result.on_error.max_attempts == 3


def test_step_with_timeout_expect_timeout_set() -> None:
    """step(action, timeout=)이 timeout을 설정하는지 검증한다."""
    result = step(_action, timeout=timedelta(seconds=30))
    assert isinstance(result, SagaStep)
    assert result.timeout == timedelta(seconds=30)


def test_step_with_compensate_and_timeout_expect_transaction_with_timeout() -> None:
    """step(action, compensate=, timeout=)이 Transaction에 timeout을 설정하는지 검증한다."""
    result = step(_action, compensate=_compensate, timeout=timedelta(seconds=10))
    assert isinstance(result, Transaction)
    assert result.timeout == timedelta(seconds=10)


def test_step_all_params_expect_fully_configured() -> None:
    """step()의 모든 파라미터를 지정하면 올바르게 구성되는지 검증한다."""
    result = step(
        _action,
        compensate=_compensate,
        on_error=Retry(max_attempts=5, then=Skip()),
        timeout=timedelta(seconds=60),
    )
    assert isinstance(result, Transaction)
    assert result.action is _action
    assert result.compensate is _compensate
    assert isinstance(result.on_error, Retry)
    assert result.on_error.max_attempts == 5
    assert result.timeout == timedelta(seconds=60)


# --- parallel() ---


def test_parallel_two_steps_expect_parallel_group() -> None:
    """parallel(step1, step2)이 Parallel을 반환하는지 검증한다."""
    s1 = SagaStep(action=_action)
    s2 = SagaStep(action=_action2)
    result = parallel(s1, s2)
    assert isinstance(result, Parallel)
    assert len(result.items) == 2
    assert result.items[0] is s1
    assert result.items[1] is s2


def test_parallel_auto_promote_callable_expect_saga_step() -> None:
    """parallel()에 callable을 넘기면 SagaStep으로 자동 승격되는지 검증한다."""
    s1 = SagaStep(action=_action)
    result = parallel(s1, _action2)
    assert isinstance(result, Parallel)
    assert len(result.items) == 2
    assert result.items[0] is s1
    assert isinstance(result.items[1], SagaStep)
    assert result.items[1].action is _action2


def test_parallel_all_callables_expect_all_promoted() -> None:
    """parallel()에 모든 callable을 넘기면 전부 SagaStep으로 승격되는지 검증한다."""
    result = parallel(_action, _action2)
    assert isinstance(result, Parallel)
    assert len(result.items) == 2
    assert isinstance(result.items[0], SagaStep)
    assert isinstance(result.items[1], SagaStep)
    assert result.items[0].action is _action
    assert result.items[1].action is _action2


def test_parallel_with_transactions_expect_preserved() -> None:
    """parallel()에 Transaction을 넘기면 보존되는지 검증한다."""
    txn1 = Transaction(action=_action, compensate=_compensate)
    txn2 = Transaction(action=_action2, compensate=_compensate2)
    result = parallel(txn1, txn2)
    assert isinstance(result, Parallel)
    assert result.items[0] is txn1
    assert result.items[1] is txn2


def test_parallel_with_nested_parallel_expect_flattened() -> None:
    """parallel()에 Parallel을 넘기면 items가 펼쳐지는지 검증한다."""
    s1 = SagaStep(action=_action)
    s2 = SagaStep(action=_action2)
    inner = Parallel(items=(s1, s2))
    s3 = SagaStep(action=_action)
    result = parallel(inner, s3)
    assert isinstance(result, Parallel)
    assert len(result.items) == 3
    assert result.items[0] is s1
    assert result.items[1] is s2
    assert result.items[2] is s3


def test_parallel_empty_expect_error() -> None:
    """parallel()에 아이템이 없으면 SagaFlowDefinitionError가 발생하는지 검증한다."""
    with pytest.raises(SagaFlowDefinitionError):
        parallel()


def test_parallel_single_item_expect_error() -> None:
    """parallel()에 아이템이 1개면 SagaFlowDefinitionError가 발생하는지 검증한다."""
    with pytest.raises(SagaFlowDefinitionError):
        parallel(SagaStep(action=_action))


def test_parallel_invalid_item_type_expect_error() -> None:
    """parallel()에 유효하지 않은 타입을 넘기면 SagaFlowDefinitionError가 발생하는지 검증한다."""
    with pytest.raises(SagaFlowDefinitionError):
        parallel("not_a_flow_item", SagaStep(action=_action))  # type: ignore[arg-type] - intentional invalid type for test


# --- saga_flow() ---


def test_saga_flow_single_step_expect_flow() -> None:
    """saga_flow(step)이 SagaFlow를 반환하는지 검증한다."""
    s = SagaStep(action=_action)
    result = saga_flow(s)
    assert isinstance(result, SagaFlow)
    assert len(result.items) == 1
    assert result.items[0] is s


def test_saga_flow_multiple_steps_expect_flow() -> None:
    """saga_flow(step1, step2)이 순서대로 SagaFlow를 구성하는지 검증한다."""
    s1 = SagaStep(action=_action)
    s2 = SagaStep(action=_action2)
    result = saga_flow(s1, s2)
    assert isinstance(result, SagaFlow)
    assert len(result.items) == 2
    assert result.items[0] is s1
    assert result.items[1] is s2


def test_saga_flow_auto_promote_callable_expect_saga_step() -> None:
    """saga_flow()에 callable을 넘기면 SagaStep으로 자동 승격되는지 검증한다."""
    result = saga_flow(_action, _action2)
    assert isinstance(result, SagaFlow)
    assert len(result.items) == 2
    assert isinstance(result.items[0], SagaStep)
    assert isinstance(result.items[1], SagaStep)
    assert result.items[0].action is _action
    assert result.items[1].action is _action2


def test_saga_flow_mixed_items_expect_promoted_and_preserved() -> None:
    """saga_flow()에 혼합 아이템을 넘기면 callable은 승격, 나머지는 보존되는지 검증한다."""
    txn = Transaction(action=_action, compensate=_compensate)
    par = Parallel(items=(SagaStep(action=_action), SagaStep(action=_action2)))
    result = saga_flow(txn, _action2, par)
    assert isinstance(result, SagaFlow)
    assert len(result.items) == 3
    assert result.items[0] is txn
    assert isinstance(result.items[1], SagaStep)
    assert result.items[1].action is _action2
    assert result.items[2] is par


def test_saga_flow_empty_expect_error() -> None:
    """saga_flow()에 아이템이 없으면 SagaFlowDefinitionError가 발생하는지 검증한다."""
    with pytest.raises(SagaFlowDefinitionError):
        saga_flow()


def test_saga_flow_invalid_item_type_expect_error() -> None:
    """saga_flow()에 유효하지 않은 타입을 넘기면 SagaFlowDefinitionError가 발생하는지 검증한다."""
    with pytest.raises(SagaFlowDefinitionError):
        saga_flow(42)  # type: ignore[arg-type] - intentional invalid type for test


def test_saga_flow_with_lambda_expect_auto_promoted() -> None:
    """saga_flow()에 람다를 넘기면 SagaStep으로 자동 승격되는지 검증한다."""
    result = saga_flow(
        lambda d: _action(d),
        lambda d: _action2(d),
    )
    assert isinstance(result, SagaFlow)
    assert len(result.items) == 2
    assert isinstance(result.items[0], SagaStep)
    assert isinstance(result.items[1], SagaStep)


def test_saga_flow_chaining_after_builder_expect_timeout_set() -> None:
    """saga_flow() 결과에 .timeout()을 체이닝할 수 있는지 검증한다."""
    result = saga_flow(_action).timeout(timedelta(minutes=5))
    assert isinstance(result, SagaFlow)
    assert result.saga_timeout == timedelta(minutes=5)


def test_saga_flow_chaining_on_compensation_failure_expect_handler_set() -> None:
    """saga_flow() 결과에 .on_compensation_failure()를 체이닝할 수 있는지 검증한다."""
    result = saga_flow(_action).on_compensation_failure(_compensate)
    assert isinstance(result, SagaFlow)
    assert result.compensation_failure_handler is _compensate


# --- Operator equivalence ---


def test_step_with_compensate_equivalent_to_rshift_expect_same_result() -> None:
    """step(a, compensate=b)이 SagaStep(a) >> b와 동일한 결과를 생성하는지 검증한다."""
    via_func = step(_action, compensate=_compensate)
    via_op = SagaStep(action=_action) >> _compensate
    assert isinstance(via_func, Transaction)
    assert isinstance(via_op, Transaction)
    assert via_func.action is via_op.action
    assert via_func.compensate is via_op.compensate
    assert type(via_func.on_error) is type(via_op.on_error)


def test_parallel_func_equivalent_to_and_operator_expect_same_items() -> None:
    """parallel(a, b)이 a & b와 동일한 결과를 생성하는지 검증한다."""
    s1 = SagaStep(action=_action)
    s2 = SagaStep(action=_action2)
    via_func = parallel(s1, s2)
    via_op = s1 & s2
    assert isinstance(via_func, Parallel)
    assert isinstance(via_op, Parallel)
    assert len(via_func.items) == len(via_op.items)
    assert via_func.items[0] is via_op.items[0]
    assert via_func.items[1] is via_op.items[1]


def test_step_with_on_error_equivalent_to_or_operator_expect_same_strategy() -> None:
    """step(a, on_error=Skip())이 SagaStep(a) | Skip()와 동일한 결과를 생성하는지 검증한다."""
    via_func = step(_action, on_error=Skip())
    via_op = SagaStep(action=_action) | Skip()
    assert isinstance(via_func, SagaStep)
    assert isinstance(via_op, SagaStep)
    assert via_func.action is via_op.action
    assert type(via_func.on_error) is type(via_op.on_error)


def test_step_compensate_on_error_equivalent_to_rshift_or_expect_same() -> None:
    """step(a, compensate=b, on_error=Retry(3))이 (SagaStep(a) >> b) | Retry(3)과 동일한지 검증한다."""
    via_func = step(_action, compensate=_compensate, on_error=Retry(max_attempts=3))
    via_op = (SagaStep(action=_action) >> _compensate) | Retry(max_attempts=3)
    assert isinstance(via_func, Transaction)
    assert isinstance(via_op, Transaction)
    assert via_func.action is via_op.action
    assert via_func.compensate is via_op.compensate
    assert isinstance(via_func.on_error, Retry)
    assert isinstance(via_op.on_error, Retry)
    assert via_func.on_error.max_attempts == via_op.on_error.max_attempts


def test_saga_flow_operator_mix_expect_valid_flow() -> None:
    """saga_flow()에서 연산자와 함수 기반 API를 혼합하여 사용할 수 있는지 검증한다."""
    flow = saga_flow(
        step(_action, compensate=_compensate),
        SagaStep(action=_action2) >> _compensate2,
        _action,
        parallel(
            SagaStep(action=_action),
            SagaStep(action=_action2),
        ),
    )
    assert isinstance(flow, SagaFlow)
    assert len(flow.items) == 4
    assert isinstance(flow.items[0], Transaction)
    assert isinstance(flow.items[1], Transaction)
    assert isinstance(flow.items[2], SagaStep)
    assert isinstance(flow.items[3], Parallel)
