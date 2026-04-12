"""Unit tests for saga execution engine."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from time import monotonic
from uuid import UUID, uuid4

import pytest

from spakky.core.common.mutability import immutable
from spakky.saga.data import AbstractSagaData
from spakky.saga.engine import run_saga_flow
from spakky.saga.error import (
    SagaCompensationFailedError,
    SagaFlowDefinitionError,
    SagaStepTimeoutError,
)
from spakky.saga.flow import (
    Parallel,
    SagaFlow,
    SagaStep,
    Transaction,
    parallel,
    saga_flow,
    step,
)
from spakky.saga.result import StepStatus
from spakky.saga.status import SagaStatus
from spakky.saga.strategy import Compensate, ExponentialBackoff, Retry, Skip


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


# --- Retry 전략 ---


@pytest.fixture
def fake_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """asyncio.sleep을 no-op으로 대체하고 호출된 지연값을 기록한다."""
    calls: list[float] = []

    async def _fake(delay: float) -> None:
        calls.append(delay)

    monkeypatch.setattr("spakky.saga.engine._sleep", _fake)
    return calls


@pytest.mark.anyio
async def test_retry_succeeds_on_second_attempt_expect_committed(
    fake_sleep: list[float],
) -> None:
    """Retry가 2번째 시도에서 성공하면 COMPLETED를 반환한다."""
    state = {"count": 0}

    async def flaky(data: _OrderData) -> None:
        state["count"] += 1
        if state["count"] == 1:
            raise RuntimeError("first attempt fails")

    flow = saga_flow(step(flaky, on_error=Retry(max_attempts=3)))
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.COMPLETED
    assert len(result.history) == 2
    assert result.history[0].status is StepStatus.FAILED
    assert result.history[1].status is StepStatus.COMMITTED
    assert fake_sleep == [
        1.0
    ]  # one sleep between attempts 1→2 (base=1.0, delay_for(1))


@pytest.mark.anyio
async def test_retry_exhausts_then_compensate_expect_failed_and_compensated(
    fake_sleep: list[float],
) -> None:
    """Retry exhaust 시 기본 then=Compensate가 발동되어 보상까지 실행한다."""
    flow = saga_flow(
        step(_succeed, compensate=_compensate_logged),
        step(_fail, on_error=Retry(max_attempts=3)),
    )
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.FAILED
    assert result.failed_step == "_fail"
    assert len(_compensation_log) == 1
    failed_records = [r for r in result.history if r.status is StepStatus.FAILED]
    assert len(failed_records) == 3
    assert len(fake_sleep) == 2  # sleeps between attempts 1→2, 2→3


@pytest.mark.anyio
async def test_retry_exhausts_then_skip_expect_continues_to_next_step(
    fake_sleep: list[float],
) -> None:
    """Retry(then=Skip) exhaust 시 다음 step으로 진행한다."""
    flow = saga_flow(
        step(_fail, on_error=Retry(max_attempts=2, then=Skip())),
        step(_succeed),
    )
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.COMPLETED
    failed_records = [r for r in result.history if r.status is StepStatus.FAILED]
    committed_records = [r for r in result.history if r.status is StepStatus.COMMITTED]
    assert len(failed_records) == 2
    assert len(committed_records) == 1


@pytest.mark.anyio
async def test_retry_backoff_delays_expect_exponential_schedule(
    fake_sleep: list[float],
) -> None:
    """Retry가 지수 백오프 스케줄대로 sleep을 호출한다."""
    flow = saga_flow(
        step(
            _fail,
            on_error=Retry(
                max_attempts=4,
                backoff=ExponentialBackoff(base=0.5),
                then=Skip(),
            ),
        ),
    )
    data = _OrderData(order_id=uuid4())
    await run_saga_flow(flow, data)

    # sleeps before attempts 2, 3, 4 — delay_for(1..3) with base=0.5
    assert fake_sleep == [0.5, 1.0, 2.0]


# --- Skip 전략 ---


@pytest.mark.anyio
async def test_skip_strategy_expect_continues_past_failure() -> None:
    """Skip 전략 시 실패를 무시하고 다음 step을 실행한다."""
    flow = saga_flow(
        step(_fail, on_error=Skip()),
        step(_succeed),
    )
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.COMPLETED
    assert result.history[0].status is StepStatus.FAILED
    assert result.history[1].status is StepStatus.COMMITTED


@pytest.mark.anyio
async def test_skip_strategy_does_not_trigger_compensation_expect_no_calls() -> None:
    """Skip 전략 시 이전 compensate들이 실행되지 않는다."""
    flow = saga_flow(
        step(_succeed, compensate=_compensate_logged),
        step(_fail, on_error=Skip()),
        step(_succeed),
    )
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.COMPLETED
    assert len(_compensation_log) == 0


# --- Step 타임아웃 ---


async def _slow_action(data: _OrderData) -> None:
    """timeout보다 오래 걸리는 액션."""
    await asyncio.sleep(0.2)


@pytest.mark.anyio
async def test_step_timeout_expect_failed_and_compensated() -> None:
    """step timeout 초과 시 실패 처리되고 이전 compensate가 실행된다."""
    flow = saga_flow(
        step(_succeed, compensate=_compensate_logged),
        step(_slow_action, timeout=timedelta(milliseconds=20)),
    )
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.FAILED
    assert result.failed_step == "_slow_action"
    assert isinstance(result.error, SagaStepTimeoutError)
    assert len(_compensation_log) == 1


@pytest.mark.anyio
async def test_step_timeout_with_retry_expect_retried(
    fake_sleep: list[float],
) -> None:
    """step timeout + Retry 조합 — 첫 시도 timeout, 두번째 시도 성공."""
    attempt_count = {"n": 0}

    async def slow_then_fast(data: _OrderData) -> None:
        attempt_count["n"] += 1
        if attempt_count["n"] == 1:
            await asyncio.sleep(0.2)

    flow = saga_flow(
        step(
            slow_then_fast,
            on_error=Retry(max_attempts=2),
            timeout=timedelta(milliseconds=20),
        ),
    )
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.COMPLETED
    assert attempt_count["n"] == 2


# --- Saga 타임아웃 ---


@pytest.mark.anyio
async def test_saga_timeout_expect_status_timed_out() -> None:
    """saga 전체 timeout 초과 시 TIMED_OUT 상태를 반환한다."""
    flow = saga_flow(step(_slow_action)).timeout(timedelta(milliseconds=20))
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.TIMED_OUT
    assert result.failed_step is None
    assert result.error is None


@pytest.mark.anyio
async def test_saga_timeout_compensates_committed_steps_expect_compensated() -> None:
    """saga timeout 초과 시 이미 commit된 step들이 보상된다."""

    async def slow_second(data: _OrderData) -> None:
        await asyncio.sleep(0.2)

    flow = saga_flow(
        step(_succeed, compensate=_compensate_logged),
        step(slow_second),
    ).timeout(timedelta(milliseconds=50))
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.TIMED_OUT
    assert len(_compensation_log) == 1


@pytest.mark.anyio
async def test_saga_without_timeout_completes_normally() -> None:
    """saga timeout 없으면 정상 완료된다."""
    flow = saga_flow(step(_succeed))
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.COMPLETED


# --- Parallel 실행 ---


@pytest.mark.anyio
async def test_parallel_items_run_concurrently_expect_gathered() -> None:
    """병렬 아이템들이 동시 실행되어 총 시간이 순차 합보다 짧다."""
    sleep_time = 0.05

    async def sleeper(data: _OrderData) -> None:
        await asyncio.sleep(sleep_time)

    flow = saga_flow(parallel(sleeper, sleeper, sleeper))
    data = _OrderData(order_id=uuid4())
    start = monotonic()
    result = await run_saga_flow(flow, data)
    elapsed = monotonic() - start

    assert result.status is SagaStatus.COMPLETED
    # 3 items concurrently: ~sleep_time total; sequential would be 3*sleep_time.
    # Use 2.9x as a lenient bound so CI scheduler jitter doesn't flake.
    assert elapsed < sleep_time * 2.9


@pytest.mark.anyio
async def test_parallel_all_succeed_expect_completed() -> None:
    """모든 병렬 아이템 성공 시 COMPLETED를 반환한다."""
    flow = saga_flow(parallel(_succeed, _succeed))
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.COMPLETED
    assert len(result.history) == 2
    assert all(r.status is StepStatus.COMMITTED for r in result.history)


@pytest.mark.anyio
async def test_parallel_one_failure_expect_all_compensated() -> None:
    """병렬 그룹에서 하나 실패 시 성공한 것들도 보상된다."""
    flow = saga_flow(
        parallel(
            step(_succeed, compensate=_compensate_logged),
            step(_fail),
        ),
    )
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.FAILED
    assert result.failed_step == "_fail"
    assert len(_compensation_log) == 1


@pytest.mark.anyio
async def test_parallel_waits_for_all_on_failure_expect_both_finish() -> None:
    """병렬에서 하나 실패해도 다른 아이템은 완료를 기다린 후 보상된다."""
    slow_finished = {"ok": False}

    async def slow_succeed(data: _OrderData) -> None:
        await asyncio.sleep(0.03)
        slow_finished["ok"] = True

    async def slow_compensate(data: _OrderData) -> None:
        _compensation_log.append("slow")

    flow = saga_flow(
        parallel(
            step(slow_succeed, compensate=slow_compensate),
            step(_fail),
        ),
    )
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.FAILED
    assert slow_finished["ok"] is True
    assert _compensation_log == ["slow"]


@pytest.mark.anyio
async def test_parallel_with_non_default_on_error_expect_definition_error() -> None:
    """v1 parallel은 기본 Compensate 외 on_error를 허용하지 않는다."""
    flow = saga_flow(
        parallel(
            step(_succeed, on_error=Retry(max_attempts=2)),
            _succeed,
        ),
    )
    data = _OrderData(order_id=uuid4())

    with pytest.raises(SagaFlowDefinitionError):
        await run_saga_flow(flow, data)


@pytest.mark.anyio
async def test_parallel_return_values_ignored_expect_data_unchanged() -> None:
    """v1 parallel 아이템의 리턴값은 무시되어 data가 변경되지 않는다."""
    new_ticket = uuid4()

    async def returns_new_data(data: _OrderData) -> _OrderData:
        return replace(data, ticket_id=new_ticket)

    flow = saga_flow(parallel(returns_new_data, _succeed))
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.COMPLETED
    assert result.data.ticket_id is None


@pytest.mark.anyio
async def test_parallel_default_compensate_accepted_expect_ok() -> None:
    """Compensate()를 명시한 parallel 아이템은 허용된다 (v1 제약 내)."""
    flow = saga_flow(
        parallel(
            step(_succeed, on_error=Compensate()),
            step(_succeed, on_error=Compensate()),
        ),
    )
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.COMPLETED


# --- Retry + Compensation failure ---


@pytest.mark.anyio
async def test_retry_then_compensate_with_compensation_failure_expect_handler(
    fake_sleep: list[float],
) -> None:
    """Retry exhaust → Compensate 경로에서 보상 실패 시 핸들러 호출 후 에러 발생."""
    handler_called: list[bool] = []

    async def escalation(data: _OrderData) -> None:
        handler_called.append(True)

    flow = saga_flow(
        step(_succeed, compensate=_compensate_fail),
        step(_fail, on_error=Retry(max_attempts=2)),
    ).on_compensation_failure(escalation)
    data = _OrderData(order_id=uuid4())

    with pytest.raises(SagaCompensationFailedError):
        await run_saga_flow(flow, data)

    assert len(handler_called) == 1


# --- Unknown flow item ---


@pytest.mark.anyio
async def test_unknown_flow_item_expect_definition_error() -> None:
    """SagaFlow에 인식 불가능한 item이 있으면 SagaFlowDefinitionError를 발생시킨다."""
    flow = SagaFlow(items=(42,))  # type: ignore[arg-type] - intentional invalid item for test
    data = _OrderData(order_id=uuid4())

    with pytest.raises(SagaFlowDefinitionError):
        await run_saga_flow(flow, data)


# --- 추가 커버리지: Retry 성공 시 data 교체 및 compensate 등록 ---


@pytest.mark.anyio
async def test_retry_success_replaces_data_expect_updated(
    fake_sleep: list[float],
) -> None:
    """Retry 성공 시 SagaData를 반환하면 data가 교체된다."""
    state = {"count": 0}
    new_ticket = uuid4()

    async def flaky_with_data(data: _OrderData) -> _OrderData:
        state["count"] += 1
        if state["count"] == 1:
            raise RuntimeError("first fail")
        return replace(data, ticket_id=new_ticket)

    flow = saga_flow(step(flaky_with_data, on_error=Retry(max_attempts=2)))
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.COMPLETED
    assert result.data.ticket_id == new_ticket


@pytest.mark.anyio
async def test_retry_success_registers_compensate_expect_rollback_on_later_failure(
    fake_sleep: list[float],
) -> None:
    """Retry 성공 후 compensate가 등록되어 후속 실패 시 호출된다."""
    state = {"count": 0}

    async def flaky(data: _OrderData) -> None:
        state["count"] += 1
        if state["count"] == 1:
            raise RuntimeError("first fail")

    flow = saga_flow(
        step(flaky, compensate=_compensate_logged, on_error=Retry(max_attempts=2)),
        step(_fail),
    )
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.FAILED
    assert len(_compensation_log) == 1


@pytest.mark.anyio
async def test_retry_exhaust_with_then_compensate_no_prior_committed_expect_failed(
    fake_sleep: list[float],
) -> None:
    """Retry(then=Compensate) exhaust 시 보상할 step이 없어도 FAILED를 반환한다."""
    flow = saga_flow(step(_fail, on_error=Retry(max_attempts=2)))
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.FAILED


@pytest.mark.anyio
async def test_parallel_multiple_failures_expect_first_reported() -> None:
    """병렬 그룹에서 여러 아이템이 실패해도 첫 번째 실패만 failed_step으로 보고된다."""

    async def fail_a(data: _OrderData) -> None:
        raise RuntimeError("a")

    async def fail_b(data: _OrderData) -> None:
        raise RuntimeError("b")

    flow = saga_flow(parallel(fail_a, fail_b))
    data = _OrderData(order_id=uuid4())
    result = await run_saga_flow(flow, data)

    assert result.status is SagaStatus.FAILED
    assert result.failed_step == "fail_a"
