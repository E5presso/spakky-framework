"""Saga execution engine — sequential execution with reverse compensation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from time import monotonic
from typing import Awaitable, Callable, Generic, cast

from spakky.saga.data import AbstractSagaData
from spakky.saga.error import SagaCompensationFailedError, SagaFlowDefinitionError
from spakky.saga.flow import Parallel, SagaDataT, SagaFlow, SagaStep, Transaction
from spakky.saga.result import SagaResult, StepRecord, StepStatus
from spakky.saga.status import SagaStatus
from spakky.saga.strategy import Retry, Skip


_CompensableEntry = tuple[str, Callable[[SagaDataT], Awaitable[None]]]


@dataclass(slots=True)
class _ItemExecutionResult(Generic[SagaDataT]):
    """단일 flow item 실행 결과."""

    data: SagaDataT
    history: list[StepRecord] = field(default_factory=list)
    compensable: list[_CompensableEntry] = field(default_factory=list)
    terminal_status: SagaStatus | None = None
    failed_step: str | None = None
    error: Exception | None = None
    completed_at: float | None = None


async def run_saga_flow(
    flow: SagaFlow[SagaDataT],
    data: SagaDataT,
) -> SagaResult[SagaDataT]:
    """SagaFlow를 순차 실행하고, 실패 시 역순 보상을 수행한다.

    Args:
        flow: 사가 흐름 정의.
        data: 초기 사가 비즈니스 데이터.

    Returns:
        SagaResult[SagaDataT]: 사가 실행 결과.

    Raises:
        SagaCompensationFailedError: 보상 실행 중 에러 발생
            (on_compensation_failure 미설정 시).
    """
    compensable: list[_CompensableEntry] = []
    history: list[StepRecord] = []
    saga_start = monotonic()

    for item in flow.items:
        execution = await _execute_flow_item(
            item=item,
            data=data,
            saga_start=saga_start,
            saga_timeout=flow.saga_timeout,
            handler=flow.compensation_failure_handler,
        )
        data = execution.data
        history.extend(execution.history)
        compensable.extend(execution.compensable)

        if execution.terminal_status is not None:
            await _run_compensation(
                compensable=compensable,
                data=data,
                history=history,
                handler=flow.compensation_failure_handler,
            )
            return SagaResult(
                status=execution.terminal_status,
                data=data,
                failed_step=execution.failed_step,
                error=execution.error,
                history=tuple(history),
                elapsed=timedelta(seconds=monotonic() - saga_start),
            )

    return SagaResult(
        status=SagaStatus.COMPLETED,
        data=data,
        history=tuple(history),
        elapsed=timedelta(seconds=monotonic() - saga_start),
    )


async def _run_compensation(
    compensable: list[_CompensableEntry],
    data: SagaDataT,
    history: list[StepRecord],
    handler: Callable[[SagaDataT], Awaitable[None]] | None,
) -> None:
    """보상 가능한 step들을 역순으로 실행한다.

    Args:
        compensable: (이름, 보상함수) 쌍 리스트.
        data: 현재 사가 데이터.
        history: 실행 기록 (in-place 추가).
        handler: 보상 실패 시 에스컬레이션 핸들러.

    Raises:
        SagaCompensationFailedError: 보상 실행 중 에러 발생 시.
    """
    for comp_name, comp_fn in reversed(compensable):
        comp_start = monotonic()
        try:
            await comp_fn(data)
            history.append(
                StepRecord(
                    name=comp_name,
                    status=StepStatus.COMPENSATED,
                    elapsed=timedelta(seconds=monotonic() - comp_start),
                )
            )
        except Exception as comp_error:  # noqa: BLE001 - compensation failure handling
            history.append(
                StepRecord(
                    name=comp_name,
                    status=StepStatus.FAILED,
                    elapsed=timedelta(seconds=monotonic() - comp_start),
                )
            )
            if handler is not None:
                await handler(data)
            raise SagaCompensationFailedError() from comp_error


async def _execute_flow_item(
    item: SagaStep[SagaDataT]
    | Transaction[SagaDataT]
    | Parallel[SagaDataT]
    | Callable[[SagaDataT], Awaitable[SagaDataT | None]],
    data: SagaDataT,
    saga_start: float,
    saga_timeout: timedelta | None,
    handler: Callable[[SagaDataT], Awaitable[None]] | None,
) -> _ItemExecutionResult[SagaDataT]:
    """Flow item을 실행한다."""
    promoted = _promote_flow_item(item)
    if isinstance(promoted, Parallel):
        return await _execute_parallel_item(
            item=promoted,
            data=data,
            saga_start=saga_start,
            saga_timeout=saga_timeout,
            handler=handler,
        )
    return await _execute_step_item(
        item=promoted,
        data=data,
        saga_start=saga_start,
        saga_timeout=saga_timeout,
        allow_data_update=True,
    )


async def _execute_parallel_item(
    item: Parallel[SagaDataT],
    data: SagaDataT,
    saga_start: float,
    saga_timeout: timedelta | None,
    handler: Callable[[SagaDataT], Awaitable[None]] | None,
) -> _ItemExecutionResult[SagaDataT]:
    """Parallel 그룹을 동시 실행한다."""
    tasks = [
        _execute_step_item(
            item=child,
            data=data,
            saga_start=saga_start,
            saga_timeout=saga_timeout,
            allow_data_update=False,
        )
        for child in item.items
    ]
    results = await asyncio.gather(*tasks)

    history: list[StepRecord] = []
    completed_results: list[_ItemExecutionResult[SagaDataT]] = []
    first_terminal: _ItemExecutionResult[SagaDataT] | None = None
    timeout_terminal: _ItemExecutionResult[SagaDataT] | None = None

    for result in results:
        history.extend(result.history)
        if result.terminal_status is None:
            completed_results.append(result)
            continue
        if result.terminal_status is SagaStatus.TIMED_OUT and timeout_terminal is None:
            timeout_terminal = result
        if first_terminal is None:
            first_terminal = result

    completed_results.sort(
        key=lambda result: result.completed_at if result.completed_at is not None else 0
    )
    compensable: list[_CompensableEntry] = []
    for result in completed_results:
        compensable.extend(result.compensable)

    terminal = timeout_terminal if timeout_terminal is not None else first_terminal

    if terminal is None:
        return _ItemExecutionResult(data=data, history=history, compensable=compensable)

    await _run_compensation(
        compensable=compensable,
        data=data,
        history=history,
        handler=handler,
    )
    return _ItemExecutionResult(
        data=data,
        history=history,
        terminal_status=terminal.terminal_status,
        failed_step=terminal.failed_step,
        error=terminal.error,
    )


async def _execute_step_item(
    item: SagaStep[SagaDataT] | Transaction[SagaDataT],
    data: SagaDataT,
    saga_start: float,
    saga_timeout: timedelta | None,
    *,
    allow_data_update: bool,
) -> _ItemExecutionResult[SagaDataT]:
    """단일 step 또는 transaction을 실행한다."""
    step_name = _resolve_step_name(item.action)
    step_start = monotonic()
    attempts = 0

    while True:
        attempts += 1
        remaining_saga = _remaining_saga_seconds(
            saga_timeout=saga_timeout,
            saga_start=saga_start,
        )
        if remaining_saga is not None and remaining_saga <= 0:
            return _terminal_timeout_result(
                step_name=step_name, data=data, step_start=step_start
            )

        timeout_seconds = _resolve_timeout_seconds(
            step_timeout=item.timeout,
            remaining_saga=remaining_saga,
        )

        try:
            result = await _await_with_timeout(item.action(data), timeout_seconds)
            completed_at = monotonic()
            resolved_data = data
            if allow_data_update and isinstance(result, AbstractSagaData):
                resolved_data = cast(SagaDataT, result)

            compensable: list[_CompensableEntry] = []
            if isinstance(item, Transaction):
                compensable.append((step_name, item.compensate))

            return _ItemExecutionResult(
                data=resolved_data,
                history=[
                    StepRecord(
                        name=step_name,
                        status=StepStatus.COMMITTED,
                        elapsed=timedelta(seconds=completed_at - step_start),
                    )
                ],
                compensable=compensable,
                completed_at=completed_at,
            )
        except Exception as error:  # noqa: BLE001 - saga engine catches all step errors
            if _is_saga_timeout(saga_timeout=saga_timeout, saga_start=saga_start):
                return _terminal_timeout_result(
                    step_name=step_name,
                    data=data,
                    step_start=step_start,
                    error=error,
                )

            retry = item.on_error if isinstance(item.on_error, Retry) else None
            if retry is not None and attempts < retry.max_attempts:
                await _sleep_backoff(
                    retry=retry,
                    attempts=attempts,
                    saga_timeout=saga_timeout,
                    saga_start=saga_start,
                )
                continue

            return _resolve_terminal_strategy(
                item=item,
                data=data,
                step_name=step_name,
                step_start=step_start,
                error=error,
            )


def _promote_flow_item(
    item: SagaStep[SagaDataT]
    | Transaction[SagaDataT]
    | Parallel[SagaDataT]
    | Callable[[SagaDataT], Awaitable[SagaDataT | None]],
) -> SagaStep[SagaDataT] | Transaction[SagaDataT] | Parallel[SagaDataT]:
    """런타임 실행용 FlowItem으로 승격한다."""
    if isinstance(item, (SagaStep, Transaction, Parallel)):
        return item
    if callable(item):
        return SagaStep(action=item)
    raise SagaFlowDefinitionError


def _resolve_terminal_strategy(
    item: SagaStep[SagaDataT] | Transaction[SagaDataT],
    data: SagaDataT,
    step_name: str,
    step_start: float,
    error: Exception,
) -> _ItemExecutionResult[SagaDataT]:
    """최종 에러 전략을 적용한다."""
    strategy = item.on_error.then if isinstance(item.on_error, Retry) else item.on_error
    result = _ItemExecutionResult(
        data=data,
        history=[
            StepRecord(
                name=step_name,
                status=StepStatus.FAILED,
                elapsed=timedelta(seconds=monotonic() - step_start),
            )
        ],
    )
    if isinstance(strategy, Skip):
        return result
    result.terminal_status = SagaStatus.FAILED
    result.failed_step = step_name
    result.error = error
    return result


def _terminal_timeout_result(
    step_name: str,
    data: SagaDataT,
    step_start: float,
    error: Exception | None = None,
) -> _ItemExecutionResult[SagaDataT]:
    """타임아웃 종료 결과를 생성한다."""
    return _ItemExecutionResult(
        data=data,
        history=[
            StepRecord(
                name=step_name,
                status=StepStatus.FAILED,
                elapsed=timedelta(seconds=monotonic() - step_start),
            )
        ],
        terminal_status=SagaStatus.TIMED_OUT,
        failed_step=step_name,
        error=error if error is not None else TimeoutError(),
    )


async def _await_with_timeout(
    task: Awaitable[SagaDataT | None],
    timeout_seconds: float | None,
) -> SagaDataT | None:
    """필요 시 wait_for를 통해 액션을 실행한다."""
    if timeout_seconds is None:
        return await task
    return await asyncio.wait_for(task, timeout=timeout_seconds)


def _resolve_timeout_seconds(
    step_timeout: timedelta | None,
    remaining_saga: float | None,
) -> float | None:
    """step 실행에 적용할 timeout 초를 계산한다."""
    step_seconds = None if step_timeout is None else step_timeout.total_seconds()
    if remaining_saga is None:
        return step_seconds
    if step_seconds is None:
        return remaining_saga
    return min(step_seconds, remaining_saga)


def _remaining_saga_seconds(
    saga_timeout: timedelta | None,
    saga_start: float,
) -> float | None:
    """남은 saga timeout budget을 계산한다."""
    if saga_timeout is None:
        return None
    return saga_timeout.total_seconds() - (monotonic() - saga_start)


def _is_saga_timeout(
    saga_timeout: timedelta | None,
    saga_start: float,
) -> bool:
    """사가 전체 timeout이 소진됐는지 확인한다."""
    remaining = _remaining_saga_seconds(
        saga_timeout=saga_timeout,
        saga_start=saga_start,
    )
    return remaining is not None and remaining <= 0


async def _sleep_backoff(
    retry: Retry,
    attempts: int,
    saga_timeout: timedelta | None,
    saga_start: float,
) -> None:
    """재시도 전 지수 백오프를 적용한다."""
    delay_seconds = retry.backoff.base * (2 ** (attempts - 1))
    if delay_seconds <= 0:
        return

    remaining_saga = _remaining_saga_seconds(
        saga_timeout=saga_timeout,
        saga_start=saga_start,
    )
    if remaining_saga is not None and remaining_saga <= 0:
        return

    if remaining_saga is None:
        await asyncio.sleep(delay_seconds)
        return
    await asyncio.sleep(min(delay_seconds, remaining_saga))


def _resolve_step_name(
    action: Callable[[SagaDataT], Awaitable[SagaDataT | None]],
) -> str:
    """step 이름을 함수명에서 추출한다."""
    # dynamic __name__ access: runtime function name for logging/debugging
    return getattr(action, "__name__", "<unknown>")
