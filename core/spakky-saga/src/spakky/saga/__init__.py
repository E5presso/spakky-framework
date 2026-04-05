"""Spakky Saga package - Distributed transaction saga orchestration."""

from spakky.core.application.plugin import Plugin
from spakky.saga.error import (
    AbstractSpakkySagaError,
    SagaCompensationFailedError,
    SagaFlowDefinitionError,
    SagaParallelMergeConflictError,
)
from spakky.saga.models.error_strategy import (
    Compensate,
    ErrorStrategy,
    Retry,
    Skip,
    exponential,
)
from spakky.saga.models.flow import (
    ActionFn,
    CompensateFn,
    FlowItem,
    Parallel,
    SagaFlow,
    SagaStep,
    Transaction,
)
from spakky.saga.models.saga_data import AbstractSagaData
from spakky.saga.models.saga_result import SagaResult, StepRecord
from spakky.saga.models.saga_status import SagaStatus

PLUGIN_NAME = Plugin(name="spakky-saga")
"""Plugin identifier for the Spakky Saga package."""

__all__ = [
    # Domain Models
    "AbstractSagaData",
    # Status
    "SagaStatus",
    # Result
    "SagaResult",
    "StepRecord",
    # Flow Types
    "SagaStep",
    "Transaction",
    "Parallel",
    "SagaFlow",
    # Type Aliases
    "ActionFn",
    "CompensateFn",
    "FlowItem",
    # Error Strategies
    "Compensate",
    "Skip",
    "Retry",
    "ErrorStrategy",
    "exponential",
    # Errors
    "AbstractSpakkySagaError",
    "SagaFlowDefinitionError",
    "SagaCompensationFailedError",
    "SagaParallelMergeConflictError",
    # Plugin
    "PLUGIN_NAME",
]
