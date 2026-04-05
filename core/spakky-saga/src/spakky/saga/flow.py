"""Saga flow composition types and type aliases."""

from __future__ import annotations

from dataclasses import field, replace
from datetime import timedelta
from typing import Awaitable, Callable, Generic, TypeAlias, TypeVar

from spakky.core.common.mutability import immutable
from spakky.saga.data import AbstractSagaData
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

    def __rshift__(
        self,
        compensate: Callable[[SagaDataT], Awaitable[None]],
    ) -> Transaction[SagaDataT]:
        return Transaction(
            action=self.action,
            compensate=compensate,
            on_error=self.on_error,
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
        """사가 전체 타임아웃을 설정한다."""
        return replace(self, saga_timeout=duration)

    def on_compensation_failure(
        self,
        handler: Callable[[SagaDataT], Awaitable[None]],
    ) -> SagaFlow[SagaDataT]:
        """보상 실패 시 에스컬레이션 핸들러를 설정한다."""
        return replace(self, compensation_failure_handler=handler)
