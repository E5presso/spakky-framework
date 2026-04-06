"""Unit tests for saga execution engine."""

from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from spakky.core.common.mutability import immutable
from spakky.saga.data import AbstractSagaData
from spakky.saga.engine import run_saga_flow
from spakky.saga.error import SagaCompensationFailedError
from spakky.saga.flow import (
    Parallel,
    SagaFlow,
    SagaStep,
    Transaction,
    saga_flow,
    step,
)
from spakky.saga.result import StepStatus
from spakky.saga.status import SagaStatus


@immutable
class _OrderData(AbstractSagaData):
    order_id: UUID
    ticket_id: UUID | None = None


# --- 헬퍼 ---


async def _succeed(data: _OrderData) -> None:
    """성공하는 액션."""


async def _succeed_with_data(data: _OrderData) -> _OrderData:
    """SagaData를 반환하는 액션."""
    return replace(data, ticket_id=uuid4())


async def _fail(data: _OrderData) -> None:
    """항상 실패하는 액션."""
    raise RuntimeError("step failed")


async def _compensate_noop(data: _OrderData) -> None:
    """보상 no-op."""


_compensation_log: list[str] = []


async def _compensate_logged(data: _OrderData) -> None:
    """보상 호출을 기록한다."""
    _compensation_log.append("compensated")


async def _compensate_fail(data: _OrderData) -> None:
    """항상 실패하는 보상."""
    raise RuntimeError("compensation failed")


@pytest.fixture(autouse=True)
def _clear_log() -> None:
    _compensation_log.clear()


# --- 정상 실행 ---


@pytest.mark.anyio
async def test_all_steps_succeed_expect_completed() -> None:
    """모든 step이 성공하면 COMPLETED 상태를 반환하는지 검증한다."""
    flow = saga_flow(
        step(_succeed),
        step(_succeed),
    )
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.COMPLETED
    assert result.data is data
    assert result.failed_step is None
    assert result.error is None
    assert len(result.history) == 2
    assert all(r.status is StepStatus.COMMITTED for r in result.history)
    assert result.elapsed > timedelta()


@pytest.mark.anyio
async def test_data_replacement_expect_updated_data() -> None:
    """SagaData 서브타입을 반환하면 data가 교체되는지 검증한다."""
    flow = saga_flow(step(_succeed_with_data))
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.COMPLETED
    assert result.data is not data
    assert result.data.ticket_id is not None
    assert result.data.order_id == data.order_id


@pytest.mark.anyio
async def test_non_saga_data_return_expect_data_preserved() -> None:
    """SagaData가 아닌 값을 반환하면 기존 data가 유지되는지 검증한다."""

    async def return_string(data: _OrderData) -> str:  # type: ignore[override] - intentional non-SagaData return for test
        return "not saga data"

    flow = saga_flow(step(return_string))  # type: ignore[arg-type] - intentional for test
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.COMPLETED
    assert result.data is data


@pytest.mark.anyio
async def test_none_return_expect_data_preserved() -> None:
    """None을 반환하면 기존 data가 유지되는지 검증한다."""
    flow = saga_flow(step(_succeed))
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.COMPLETED
    assert result.data is data


# --- 실패 & 보상 ---


@pytest.mark.anyio
async def test_step_failure_expect_failed_and_compensated() -> None:
    """step 실패 시 이전 compensate를 역순 실행하고 FAILED를 반환하는지 검증한다."""
    flow = saga_flow(
        step(_succeed, compensate=_compensate_logged),
        step(_fail),
    )
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.FAILED
    assert result.failed_step == "_fail"
    assert isinstance(result.error, RuntimeError)
    assert len(_compensation_log) == 1
    assert len(result.history) == 3
    assert result.history[0].status is StepStatus.COMMITTED
    assert result.history[1].status is StepStatus.FAILED
    assert result.history[2].status is StepStatus.COMPENSATED


@pytest.mark.anyio
async def test_failure_skips_steps_without_compensate_expect_only_compensable() -> None:
    """compensate가 없는 step은 보상에서 건너뛰는지 검증한다."""
    flow = saga_flow(
        step(_succeed, compensate=_compensate_logged),
        step(_succeed),  # compensate 없음
        step(_fail),
    )
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.FAILED
    assert len(_compensation_log) == 1
    # history: commit(0), commit(1), fail(2), compensate(0)
    assert len(result.history) == 4
    assert result.history[3].status is StepStatus.COMPENSATED


@pytest.mark.anyio
async def test_reverse_compensation_order_expect_lifo() -> None:
    """보상이 역순(LIFO)으로 실행되는지 검증한다."""
    order_log: list[str] = []

    async def comp_a(data: _OrderData) -> None:
        order_log.append("a")

    async def comp_b(data: _OrderData) -> None:
        order_log.append("b")

    flow = saga_flow(
        step(_succeed, compensate=comp_a),
        step(_succeed, compensate=comp_b),
        step(_fail),
    )
    data = _OrderData(order_id=uuid4())
    await run_saga_flow(flow, data)

    assert order_log == ["b", "a"]


@pytest.mark.anyio
async def test_first_step_fails_expect_no_compensation() -> None:
    """첫 번째 step이 실패하면 보상할 step이 없어 바로 FAILED를 반환하는지 검증한다."""
    flow = saga_flow(step(_fail))
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.FAILED
    assert result.failed_step == "_fail"
    assert len(result.history) == 1
    assert result.history[0].status is StepStatus.FAILED


# --- Transaction (>> 연산자) ---


@pytest.mark.anyio
async def test_transaction_success_expect_completed() -> None:
    """Transaction(>> 연산자)이 성공하면 COMPLETED를 반환하는지 검증한다."""
    txn = Transaction(action=_succeed, compensate=_compensate_noop)
    flow = SagaFlow(items=(txn,))
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.COMPLETED


@pytest.mark.anyio
async def test_transaction_failure_expect_compensated() -> None:
    """Transaction 이후 step 실패 시 Transaction의 compensate가 호출되는지 검증한다."""
    flow = saga_flow(
        step(_succeed, compensate=_compensate_logged),
        step(_fail),
    )
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.FAILED
    assert len(_compensation_log) == 1


# --- Parallel (순차 실행 폴백) ---


@pytest.mark.anyio
async def test_parallel_items_execute_sequentially_expect_completed() -> None:
    """Parallel 아이템이 순차적으로 실행되어 COMPLETED를 반환하는지 검증한다."""
    par = Parallel(
        items=(
            SagaStep(action=_succeed),
            SagaStep(action=_succeed),
        ),
    )
    flow = SagaFlow(items=(par,))
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.COMPLETED
    assert len(result.history) == 2


# --- history 기록 ---


@pytest.mark.anyio
async def test_history_records_step_names_expect_function_names() -> None:
    """history에 함수 이름이 기록되는지 검증한다."""
    flow = saga_flow(step(_succeed), step(_succeed_with_data))
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.history[0].name == "_succeed"
    assert result.history[1].name == "_succeed_with_data"


@pytest.mark.anyio
async def test_history_records_elapsed_expect_positive_durations() -> None:
    """history에 양수 소요 시간이 기록되는지 검증한다."""
    flow = saga_flow(step(_succeed))
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.history[0].elapsed >= timedelta()


@pytest.mark.anyio
async def test_saga_elapsed_expect_positive() -> None:
    """사가 전체 소요 시간이 양수인지 검증한다."""
    flow = saga_flow(step(_succeed))
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.elapsed > timedelta()


# --- 보상 실패 ---


@pytest.mark.anyio
async def test_compensation_failure_no_handler_expect_error() -> None:
    """보상 실패 시 핸들러 없으면 SagaCompensationFailedError가 발생하는지 검증한다."""
    flow = saga_flow(
        step(_succeed, compensate=_compensate_fail),
        step(_fail),
    )
    data = _OrderData(order_id=uuid4())

    with pytest.raises(SagaCompensationFailedError):
        await run_saga_flow(flow, data)


@pytest.mark.anyio
async def test_compensation_failure_with_handler_expect_handler_called() -> None:
    """보상 실패 시 핸들러가 호출된 후 SagaCompensationFailedError가 발생하는지 검증한다."""
    handler_called: list[bool] = []

    async def escalation_handler(data: _OrderData) -> None:
        handler_called.append(True)

    flow = saga_flow(
        step(_succeed, compensate=_compensate_fail),
        step(_fail),
    ).on_compensation_failure(escalation_handler)
    data = _OrderData(order_id=uuid4())

    with pytest.raises(SagaCompensationFailedError):
        await run_saga_flow(flow, data)

    assert len(handler_called) == 1


# --- 람다 자동 처리 ---


@pytest.mark.anyio
async def test_lambda_returning_saga_data_expect_data_replaced() -> None:
    """람다가 SagaData를 반환하면 data가 교체되는지 검증한다."""
    new_ticket = uuid4()
    flow = saga_flow(
        step(lambda d: _make_awaitable(replace(d, ticket_id=new_ticket))),
    )
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.COMPLETED
    assert result.data.ticket_id == new_ticket
    assert result.history[0].name == "<lambda>"


async def _make_awaitable(value: _OrderData) -> _OrderData:
    """동기 값을 Awaitable로 감싼다."""
    return value
