"""Saga execution engine — sequential execution with reverse compensation."""

from __future__ import annotations

from datetime import timedelta
from time import monotonic
from typing import Awaitable, Callable

from spakky.saga.data import AbstractSagaData
from spakky.saga.error import SagaCompensationFailedError, SagaFlowDefinitionError
from spakky.saga.flow import Parallel, SagaDataT, SagaFlow, SagaStep, Transaction
from spakky.saga.result import SagaResult, StepRecord, StepStatus
from spakky.saga.status import SagaStatus


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
    normalized = _normalize_items(
        flow.items  # pyrefly: ignore - saga_flow() promotes Callable to SagaStep before engine sees it
    )
    compensable: list[tuple[str, Callable[[SagaDataT], Awaitable[None]]]] = []
    history: list[StepRecord] = []
    saga_start = monotonic()

    for name, action, compensate in normalized:
        step_start = monotonic()
        try:
            result = await action(data)
            if isinstance(result, AbstractSagaData):
                data = result  # type: ignore[assignment] - runtime SagaData subtype check
            step_elapsed = timedelta(seconds=monotonic() - step_start)
            history.append(
                StepRecord(
                    name=name,
                    status=StepStatus.COMMITTED,
                    elapsed=step_elapsed,
                )
            )
            if compensate is not None:
                compensable.append((name, compensate))
        except Exception as error:  # noqa: BLE001 - saga engine catches all step errors
            step_elapsed = timedelta(seconds=monotonic() - step_start)
            history.append(
                StepRecord(
                    name=name,
                    status=StepStatus.FAILED,
                    elapsed=step_elapsed,
                )
            )
            await _run_compensation(
                compensable=compensable,
                data=data,
                history=history,
                handler=flow.compensation_failure_handler,
            )
            return SagaResult(
                status=SagaStatus.FAILED,
                data=data,
                failed_step=name,
                error=error,
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
    compensable: list[tuple[str, Callable[[SagaDataT], Awaitable[None]]]],
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


_NormalizedStep = tuple[
    str,
    Callable[[SagaDataT], Awaitable[SagaDataT | None]],
    Callable[[SagaDataT], Awaitable[None]] | None,
]
"""(name, action, compensate_or_none) 튜플."""


def _normalize_items(
    items: tuple[  # pyrefly: ignore - SagaFlow.items union includes Callable but saga_flow() promotes it
        SagaStep[SagaDataT] | Transaction[SagaDataT] | Parallel[SagaDataT], ...
    ],
) -> list[_NormalizedStep[SagaDataT]]:
    """flow items를 (name, action, compensate) 튜플 리스트로 정규화한다."""
    result: list[_NormalizedStep[SagaDataT]] = []
    for item in items:
        if isinstance(item, Transaction):
            name = getattr(item.action, "__name__", "<unknown>")
            result.append((name, item.action, item.compensate))
        elif isinstance(item, SagaStep):
            name = getattr(item.action, "__name__", "<unknown>")
            result.append((name, item.action, None))
        elif isinstance(item, Parallel):
            result.extend(_normalize_items(item.items))
        elif callable(item):
            name = getattr(item, "__name__", "<unknown>")
            result.append((name, item, None))
        else:
            raise SagaFlowDefinitionError
    return result
