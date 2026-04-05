"""Saga execution result."""

from dataclasses import field
from datetime import timedelta
from typing import Generic, TypeVar

from spakky.core.common.mutability import immutable
from spakky.saga.data import AbstractSagaData
from spakky.saga.status import SagaStatus

SagaDataT_co = TypeVar("SagaDataT_co", bound=AbstractSagaData, covariant=True)


@immutable
class StepRecord:
    """단일 step의 실행 기록."""

    name: str
    elapsed: timedelta


@immutable
class SagaResult(Generic[SagaDataT_co]):
    """사가 실행 결과. 예외를 발생시키지 않고 결과를 전달한다."""

    status: SagaStatus
    data: SagaDataT_co
    failed_step: str | None = None
    error: Exception | None = None
    history: tuple[StepRecord, ...] = field(default_factory=tuple)
    elapsed: timedelta = field(default_factory=timedelta)
