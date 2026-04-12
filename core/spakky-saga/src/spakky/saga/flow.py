"""Saga flow composition types, type aliases, and builder functions."""

from __future__ import annotations

from dataclasses import field, replace
from datetime import timedelta
from typing import Awaitable, Callable, Generic, TypeAlias, TypeVar, cast

from spakky.core.common.mutability import immutable
from spakky.saga.data import AbstractSagaData
from spakky.saga.error import SagaFlowDefinitionError
from spakky.saga.strategy import Compensate, ErrorStrategy

SagaDataT = TypeVar("SagaDataT", bound=AbstractSagaData)
"""사가 데이터 타입 변수."""

ActionFn: TypeAlias = Callable[[SagaDataT], Awaitable[SagaDataT | None]]
"""commit 액션 함수 시그니처. data를 변환하거나 None을 반환한다."""

CompensateFn: TypeAlias = Callable[[SagaDataT], Awaitable[None]]
"""보상 함수 시그니처. 부수효과만 수행한다."""


@immutable
class SagaStep(Generic[SagaDataT]):
    """개별 saga step. 연산자로 Transaction, Parallel을 구성한다."""

    action: Callable[[SagaDataT], Awaitable[SagaDataT | None]]
    on_error: ErrorStrategy = field(default_factory=Compensate)
    timeout: timedelta | None = None

    def __rshift__(
        self,
        compensate: Callable[[SagaDataT], Awaitable[None]] | SagaStep[SagaDataT],
    ) -> Transaction[SagaDataT]:
        compensate_fn: Callable[[SagaDataT], Awaitable[None]] = (
            cast(Callable[[SagaDataT], Awaitable[None]], compensate.action)
            if isinstance(compensate, SagaStep)
            else compensate
        )
        return Transaction(
            action=self.action,
            compensate=compensate_fn,
            on_error=self.on_error,
            timeout=self.timeout,
        )

    def __and__(
        self,
        other: SagaStep[SagaDataT] | Transaction[SagaDataT] | Parallel[SagaDataT],
    ) -> Parallel[SagaDataT]:
        if isinstance(other, Parallel):
            return Parallel(items=(self, *other.items))
        return Parallel(items=(self, other))

    def __or__(self, strategy: ErrorStrategy) -> SagaStep[SagaDataT]:
        return replace(self, on_error=strategy)


@immutable
class Transaction(Generic[SagaDataT]):
    """commit + compensate 쌍. >> 연산자의 결과."""

    action: Callable[[SagaDataT], Awaitable[SagaDataT | None]]
    compensate: Callable[[SagaDataT], Awaitable[None]]
    on_error: ErrorStrategy = field(default_factory=Compensate)
    timeout: timedelta | None = None

    def __and__(
        self,
        other: SagaStep[SagaDataT] | Transaction[SagaDataT] | Parallel[SagaDataT],
    ) -> Parallel[SagaDataT]:
        if isinstance(other, Parallel):
            return Parallel(items=(self, *other.items))
        return Parallel(items=(self, other))

    def __or__(self, strategy: ErrorStrategy) -> Transaction[SagaDataT]:
        return replace(self, on_error=strategy)


@immutable
class Parallel(Generic[SagaDataT]):
    """동시 실행 그룹. & 연산자의 결과."""

    items: tuple[
        SagaStep[SagaDataT] | Transaction[SagaDataT],
        ...,
    ]

    def __and__(
        self,
        other: SagaStep[SagaDataT] | Transaction[SagaDataT] | Parallel[SagaDataT],
    ) -> Parallel[SagaDataT]:
        if isinstance(other, Parallel):
            return Parallel(items=(*self.items, *other.items))
        return Parallel(items=(*self.items, other))


FlowItem: TypeAlias = (
    SagaStep[SagaDataT]
    | Transaction[SagaDataT]
    | Parallel[SagaDataT]
    | Callable[[SagaDataT], Awaitable[SagaDataT | None]]
)
"""saga_flow에 넣을 수 있는 아이템 유니온 타입."""


@immutable
class SagaFlow(Generic[SagaDataT]):
    """전체 사가 흐름 정의."""

    items: tuple[
        SagaStep[SagaDataT]
        | Transaction[SagaDataT]
        | Parallel[SagaDataT]
        | Callable[[SagaDataT], Awaitable[SagaDataT | None]],
        ...,
    ]
    saga_timeout: timedelta | None = None
    compensation_failure_handler: Callable[[SagaDataT], Awaitable[None]] | None = None

    def timeout(self, duration: timedelta) -> SagaFlow[SagaDataT]:
        """사가 전체 타임아웃을 설정한다.

        v1 제약: 타임아웃이 `parallel()` 그룹 실행 도중 만료되면, 그 그룹 내에서
        이미 성공했으나 compensable 리스트에 등록되기 전(gather 반환 전) 상태였던
        side-effect는 보상되지 않는다. 순차 step이나 이미 완료된 parallel 그룹의
        commit된 step은 정상 보상된다.
        """
        return replace(self, saga_timeout=duration)

    def on_compensation_failure(
        self,
        handler: Callable[[SagaDataT], Awaitable[None]],
    ) -> SagaFlow[SagaDataT]:
        """보상 실패 시 에스컬레이션 핸들러를 설정한다."""
        return replace(self, compensation_failure_handler=handler)


_MIN_PARALLEL_ITEMS = 2
"""parallel()에 필요한 최소 아이템 수."""


def step(
    action: Callable[[SagaDataT], Awaitable[SagaDataT | None]],
    *,
    compensate: Callable[[SagaDataT], Awaitable[None]] | None = None,
    on_error: ErrorStrategy | None = None,
    timeout: timedelta | None = None,
) -> SagaStep[SagaDataT] | Transaction[SagaDataT]:
    """commit-compensate 바인딩을 생성한다.

    Args:
        action: commit 액션 함수.
        compensate: 보상 함수. 지정 시 Transaction을 반환한다.
        on_error: 에러 전략. 미지정 시 Compensate.
        timeout: step 타임아웃.

    Returns:
        compensate 미지정 시 SagaStep, 지정 시 Transaction.
    """
    resolved_on_error: ErrorStrategy = (
        on_error if on_error is not None else Compensate()
    )
    if compensate is not None:
        return Transaction(
            action=action,
            compensate=compensate,
            on_error=resolved_on_error,
            timeout=timeout,
        )
    return SagaStep(
        action=action,
        on_error=resolved_on_error,
        timeout=timeout,
    )


def parallel(
    *items: SagaStep[SagaDataT]
    | Transaction[SagaDataT]
    | Parallel[SagaDataT]
    | Callable[[SagaDataT], Awaitable[SagaDataT | None]],
) -> Parallel[SagaDataT]:
    """동시 실행 그룹을 구성한다.

    Callable은 SagaStep으로 자동 승격된다.

    Args:
        *items: 병렬 실행할 FlowItem들. 최소 2개 필요.

    Raises:
        SagaFlowDefinitionError: 아이템이 2개 미만일 때.
    """
    if len(items) < _MIN_PARALLEL_ITEMS:
        raise SagaFlowDefinitionError
    promoted: list[SagaStep[SagaDataT] | Transaction[SagaDataT]] = []
    for item in items:
        if isinstance(item, (SagaStep, Transaction)):
            promoted.append(item)
        elif isinstance(item, Parallel):
            promoted.extend(item.items)
        elif callable(item):
            promoted.append(SagaStep(action=item))
        else:
            raise SagaFlowDefinitionError
    return Parallel(items=tuple(promoted))


def saga_flow(
    *items: SagaStep[SagaDataT]
    | Transaction[SagaDataT]
    | Parallel[SagaDataT]
    | Callable[[SagaDataT], Awaitable[SagaDataT | None]],
) -> SagaFlow[SagaDataT]:
    """사가 흐름을 정의한다.

    Callable은 SagaStep으로 자동 승격된다.

    Args:
        *items: 순차 실행할 FlowItem들. 최소 1개 필요.

    Raises:
        SagaFlowDefinitionError: 아이템이 비어있을 때.
    """
    if len(items) == 0:
        raise SagaFlowDefinitionError
    promoted: list[
        SagaStep[SagaDataT] | Transaction[SagaDataT] | Parallel[SagaDataT]
    ] = []
    for item in items:
        if isinstance(item, (SagaStep, Transaction, Parallel)):
            promoted.append(item)
        elif callable(item):
            promoted.append(SagaStep(action=item))
        else:
            raise SagaFlowDefinitionError
    return SagaFlow(items=tuple(promoted))
