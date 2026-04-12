"""Saga execution engine — sequential/parallel execution, retry, timeout, compensation."""

from __future__ import annotations

import asyncio
from asyncio import sleep as _sleep
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from time import monotonic
from typing import Awaitable, Callable, Generic

from spakky.saga.data import AbstractSagaData
from spakky.saga.error import (
    SagaCompensationFailedError,
    SagaFlowDefinitionError,
    SagaStepTimeoutError,
)
from spakky.saga.flow import (
    CompensateFn,
    Parallel,
    SagaDataT,
    SagaFlow,
    SagaStep,
    Transaction,
)
from spakky.saga.result import SagaResult, StepRecord, StepStatus
from spakky.saga.status import SagaStatus
from spakky.saga.strategy import Compensate, ErrorStrategy, Retry, Skip


@dataclass(frozen=True)
class _NormalizedStep(Generic[SagaDataT]):
    """정규화된 단일 step: 실행에 필요한 모든 메타데이터 포함."""

    name: str
    action: Callable[[SagaDataT], Awaitable[SagaDataT | None]]
    compensate: Callable[[SagaDataT], Awaitable[None]] | None
    on_error: ErrorStrategy
    step_timeout: timedelta | None


@dataclass(frozen=True)
class _NormalizedParallel(Generic[SagaDataT]):
    """정규화된 병렬 그룹. asyncio.gather로 동시 실행된다."""

    steps: tuple[_NormalizedStep[SagaDataT], ...]


class _StrategyOutcome(Enum):
    """`_apply_strategy` 반환값. 오케스트레이터가 분기 기준으로 사용한다."""

    CONTINUE = "CONTINUE"
    """다음 step으로 진행 (Skip 또는 Retry 성공)."""
    COMPENSATE_AND_FAIL = "COMPENSATE_AND_FAIL"
    """compensation 역순 실행 후 FAILED 반환."""


@dataclass
class _StrategyResult:
    """`_apply_strategy` 반환 래퍼."""

    outcome: _StrategyOutcome
    last_error: Exception


class SagaExecutor(Generic[SagaDataT]):
    """사가 실행 오케스트레이터.

    SagaFlow를 입력받아 step 단위로 실행하고, 실패 시 `on_error` 전략을 적용하며,
    필요 시 역순 보상을 수행한다. 공개 API는 `run_saga_flow(flow, data)`를 통한 얇은
    래퍼로 노출된다.
    """

    def __init__(self, flow: SagaFlow[SagaDataT], data: SagaDataT) -> None:
        self._flow = flow
        self._data: SagaDataT = data
        self._compensable: list[tuple[str, CompensateFn[SagaDataT]]] = []
        self._history: list[StepRecord] = []
        self._saga_start: float = 0.0

    async def run(self) -> SagaResult[SagaDataT]:
        """사가를 실행하고 결과를 반환한다."""
        self._saga_start = monotonic()
        normalized = self._normalize(self._flow.items)
        saga_timeout = self._flow.saga_timeout
        if saga_timeout is None:
            return await self._run_items(normalized)
        return await self._run_with_saga_timeout(normalized, saga_timeout)

    async def _run_with_saga_timeout(
        self,
        items: list[_NormalizedStep[SagaDataT] | _NormalizedParallel[SagaDataT]],
        saga_timeout: timedelta,
    ) -> SagaResult[SagaDataT]:
        """saga 전체 타임아웃을 적용한 실행. 초과 시 commit된 step을 보상한다."""
        try:
            async with asyncio.timeout(saga_timeout.total_seconds()):
                return await self._run_items(items)
        except TimeoutError:
            await self._run_compensation()
            return SagaResult(
                status=SagaStatus.TIMED_OUT,
                data=self._data,
                history=tuple(self._history),
                elapsed=timedelta(seconds=monotonic() - self._saga_start),
            )

    async def _run_items(
        self,
        items: list[_NormalizedStep[SagaDataT] | _NormalizedParallel[SagaDataT]],
    ) -> SagaResult[SagaDataT]:
        """정규화된 item 리스트를 순차 처리한다. parallel은 내부에서 gather된다."""
        for item in items:
            if isinstance(item, _NormalizedParallel):
                failure = await self._execute_parallel(item)
            else:
                failure = await self._execute_serial_step(item)
            if failure is not None:
                await self._run_compensation()
                name, error = failure
                return SagaResult(
                    status=SagaStatus.FAILED,
                    data=self._data,
                    failed_step=name,
                    error=error,
                    history=tuple(self._history),
                    elapsed=timedelta(seconds=monotonic() - self._saga_start),
                )
        return SagaResult(
            status=SagaStatus.COMPLETED,
            data=self._data,
            history=tuple(self._history),
            elapsed=timedelta(seconds=monotonic() - self._saga_start),
        )

    async def _execute_serial_step(
        self,
        step_item: _NormalizedStep[SagaDataT],
    ) -> tuple[str, Exception] | None:
        """단일 step을 실행한다. 실패 시 on_error 전략에 따라 처리한다.

        Returns:
            실패로 saga를 종료해야 하면 (step_name, error), 아니면 None.
        """
        step_start = monotonic()
        try:
            result = await self._invoke_action(step_item.action, step_item.step_timeout)
        except Exception as error:  # noqa: BLE001 - saga engine catches all step errors
            self._record(step_item.name, StepStatus.FAILED, step_start)
            strategy_result = await self._apply_strategy(step_item, error)
            if strategy_result.outcome is _StrategyOutcome.CONTINUE:
                return None
            return (step_item.name, strategy_result.last_error)
        if isinstance(result, AbstractSagaData):
            self._data = result  # type: ignore[assignment] - runtime SagaData subtype check
        self._record(step_item.name, StepStatus.COMMITTED, step_start)
        if step_item.compensate is not None:
            self._compensable.append((step_item.name, step_item.compensate))
        return None

    async def _execute_parallel(
        self,
        group: _NormalizedParallel[SagaDataT],
    ) -> tuple[str, Exception] | None:
        """병렬 그룹을 asyncio.gather로 실행한다. v1 parallel은 side-effect only.

        - 실패가 하나라도 있으면 모두 완료를 기다린 뒤 성공한 것들을 compensable에 등록,
          첫 실패의 (name, error)를 반환한다.
        - 성공한 모든 step의 compensate는 선언 순서대로 compensable에 추가되어,
          전체 saga의 역순 보상 시 동일한 LIFO 규칙을 따른다.
        - Return value는 v1에서 무시된다(self._data 변경 없음).
        """
        step_starts = [monotonic() for _ in group.steps]
        results = await asyncio.gather(
            *(
                self._invoke_action(step_item.action, step_item.step_timeout)
                for step_item in group.steps
            ),
            return_exceptions=True,
        )

        first_failure: tuple[str, Exception] | None = None
        cancellation: asyncio.CancelledError | None = None
        for step_item, started, result in zip(group.steps, step_starts, results):
            if isinstance(result, asyncio.CancelledError):
                # gather(return_exceptions=True)는 CancelledError를 반환값으로 노출한다.
                # 이를 성공으로 오인하지 않도록 별도 분기로 취소 의미를 보존한다.
                self._record(step_item.name, StepStatus.FAILED, started)
                if cancellation is None:
                    cancellation = result
            elif isinstance(result, Exception):
                self._record(step_item.name, StepStatus.FAILED, started)
                if first_failure is None:
                    first_failure = (step_item.name, result)
            else:
                self._record(step_item.name, StepStatus.COMMITTED, started)
                if step_item.compensate is not None:
                    self._compensable.append((step_item.name, step_item.compensate))
        if cancellation is not None:
            raise cancellation
        return first_failure

    async def _invoke_action(
        self,
        action: Callable[[SagaDataT], Awaitable[SagaDataT | None]],
        step_timeout: timedelta | None,
    ) -> SagaDataT | None:
        """step action을 실행한다. timeout 초과 시 SagaStepTimeoutError로 변환한다.

        `asyncio.timeout()` context manager의 `.expired()`로 실제 타임아웃 만료와
        action이 직접 `TimeoutError`를 raise한 경우를 구분한다.
        """
        if step_timeout is None:
            return await action(self._data)
        cm = asyncio.timeout(step_timeout.total_seconds())
        try:
            async with cm:
                return await action(self._data)
        except TimeoutError:
            if cm.expired():
                raise SagaStepTimeoutError from None
            raise

    async def _apply_strategy(
        self,
        step_item: _NormalizedStep[SagaDataT],
        first_error: Exception,
    ) -> _StrategyResult:
        """첫 실패 후 on_error 전략을 적용한다."""
        match (
            step_item.on_error
        ):  # pragma: no branch - exhaustive union (Skip|Retry|Compensate)
            case Skip():
                return _StrategyResult(
                    outcome=_StrategyOutcome.CONTINUE,
                    last_error=first_error,
                )
            case Retry() as retry:
                return await self._apply_retry(step_item, retry, first_error)
            case Compensate():
                return _StrategyResult(
                    outcome=_StrategyOutcome.COMPENSATE_AND_FAIL,
                    last_error=first_error,
                )

    async def _apply_retry(
        self,
        step_item: _NormalizedStep[SagaDataT],
        retry: Retry,
        first_error: Exception,
    ) -> _StrategyResult:
        """Retry 전략을 실행한다. 성공 시 CONTINUE, exhaust 시 then 전략 적용."""
        last_error: Exception = first_error
        for attempt in range(2, retry.max_attempts + 1):
            await _sleep(retry.backoff.delay_for(attempt - 1))
            step_start = monotonic()
            try:
                result = await self._invoke_action(
                    step_item.action, step_item.step_timeout
                )
            except Exception as error:  # noqa: BLE001 - saga engine catches all step errors
                last_error = error
                self._record(step_item.name, StepStatus.FAILED, step_start)
                continue
            if isinstance(result, AbstractSagaData):
                self._data = result  # type: ignore[assignment] - runtime SagaData subtype check
            self._record(step_item.name, StepStatus.COMMITTED, step_start)
            if step_item.compensate is not None:
                self._compensable.append((step_item.name, step_item.compensate))
            return _StrategyResult(
                outcome=_StrategyOutcome.CONTINUE,
                last_error=last_error,
            )
        match retry.then:  # pragma: no branch - exhaustive union (Compensate|Skip)
            case Skip():
                return _StrategyResult(
                    outcome=_StrategyOutcome.CONTINUE,
                    last_error=last_error,
                )
            case Compensate():
                return _StrategyResult(
                    outcome=_StrategyOutcome.COMPENSATE_AND_FAIL,
                    last_error=last_error,
                )

    async def _run_compensation(self) -> None:
        """보상 가능한 step들을 역순으로 실행한다.

        Raises:
            SagaCompensationFailedError: 보상 실행 중 에러 발생 시
                (on_compensation_failure 핸들러가 있어도 최종적으로 raise).
        """
        for comp_name, comp_fn in reversed(self._compensable):
            comp_start = monotonic()
            try:
                await comp_fn(self._data)
                self._record(comp_name, StepStatus.COMPENSATED, comp_start)
            except Exception as comp_error:  # noqa: BLE001 - compensation failure handling
                self._record(comp_name, StepStatus.FAILED, comp_start)
                if self._flow.compensation_failure_handler is not None:
                    await self._flow.compensation_failure_handler(self._data)
                raise SagaCompensationFailedError from comp_error

    def _record(self, name: str, status: StepStatus, start: float) -> None:
        """실행 기록 1건을 추가한다."""
        self._history.append(
            StepRecord(
                name=name,
                status=status,
                elapsed=timedelta(seconds=monotonic() - start),
            )
        )

    def _normalize(
        self,
        items: tuple[
            SagaStep[SagaDataT]
            | Transaction[SagaDataT]
            | Parallel[SagaDataT]
            | Callable[[SagaDataT], Awaitable[SagaDataT | None]],
            ...,
        ],
    ) -> list[_NormalizedStep[SagaDataT] | _NormalizedParallel[SagaDataT]]:
        """flow items를 실행 단위로 정규화한다.

        Raises:
            SagaFlowDefinitionError: Parallel 내부 step에 기본 Compensate 외 on_error가
                지정된 경우(v1 제약), 또는 item이 인식 불가능한 타입인 경우.
        """
        result: list[_NormalizedStep[SagaDataT] | _NormalizedParallel[SagaDataT]] = []
        for item in items:
            if isinstance(item, Parallel):
                result.append(self._normalize_parallel(item))
            elif isinstance(item, (SagaStep, Transaction)):
                result.append(self._normalize_step(item))
            elif callable(item):
                # dynamic __name__ access: runtime function name for logging/debugging
                name = getattr(item, "__name__", "<unknown>")
                result.append(
                    _NormalizedStep(
                        name=name,
                        action=item,
                        compensate=None,
                        on_error=Compensate(),
                        step_timeout=None,
                    )
                )
            else:
                raise SagaFlowDefinitionError
        return result

    @staticmethod
    def _normalize_step(
        item: SagaStep[SagaDataT] | Transaction[SagaDataT],
    ) -> _NormalizedStep[SagaDataT]:
        """SagaStep/Transaction을 _NormalizedStep으로 변환한다."""
        # dynamic __name__ access: runtime function name for logging/debugging
        name = getattr(item.action, "__name__", "<unknown>")
        compensate = item.compensate if isinstance(item, Transaction) else None
        return _NormalizedStep(
            name=name,
            action=item.action,
            compensate=compensate,
            on_error=item.on_error,
            step_timeout=item.timeout,
        )

    @staticmethod
    def _normalize_parallel(
        item: Parallel[SagaDataT],
    ) -> _NormalizedParallel[SagaDataT]:
        """Parallel을 _NormalizedParallel로 변환한다. v1 제약 검증 포함."""
        steps: list[_NormalizedStep[SagaDataT]] = []
        for child in item.items:
            normalized = SagaExecutor._normalize_step(child)
            if not isinstance(normalized.on_error, Compensate):
                raise SagaFlowDefinitionError
            steps.append(normalized)
        return _NormalizedParallel(steps=tuple(steps))


async def run_saga_flow(
    flow: SagaFlow[SagaDataT],
    data: SagaDataT,
) -> SagaResult[SagaDataT]:
    """SagaFlow를 실행하고 결과를 반환한다.

    Args:
        flow: 사가 흐름 정의.
        data: 초기 사가 비즈니스 데이터.

    Returns:
        SagaResult[SagaDataT]: 사가 실행 결과. 예외를 발생시키지 않는다
            (SagaCompensationFailedError 제외).

    Raises:
        SagaCompensationFailedError: 보상 실행 중 에러 발생
            (on_compensation_failure 미설정 시).
    """
    return await SagaExecutor(flow, data).run()
