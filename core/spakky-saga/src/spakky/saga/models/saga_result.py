"""Saga execution result.

This module provides SagaResult, which encapsulates the outcome of a saga
execution. Saga failures are normal business results, not exceptions.
"""

from typing import Generic, TypeVar

from spakky.core.common.mutability import immutable
from spakky.saga.error import AbstractSpakkySagaError
from spakky.saga.models.saga_data import AbstractSagaData
from spakky.saga.models.saga_status import SagaStatus

SagaDataT = TypeVar("SagaDataT", bound=AbstractSagaData)


@immutable
class StepRecord:
    """Record of a single step execution.

    Attributes:
        name: The name of the step.
        elapsed: Time taken to execute the step in seconds.
    """

    name: str
    elapsed: float


@immutable
class SagaResult(Generic[SagaDataT]):
    """Result of a saga execution.

    Saga failures are normal business outcomes and do not raise exceptions.
    Use ``status`` to check the outcome and ``error`` for failure details.

    Attributes:
        status: Final execution status of the saga.
        data: The final SagaData after execution (business data).
        failed_step: Name of the step that failed, or None if successful.
        error: The exception that caused the failure, or None if successful.
        history: Ordered list of step execution records.
        elapsed: Total time taken for the saga execution in seconds.
    """

    status: SagaStatus
    data: SagaDataT
    failed_step: str | None = None
    error: AbstractSpakkySagaError | None = None
    history: tuple[StepRecord, ...] = ()
    elapsed: float = 0.0
