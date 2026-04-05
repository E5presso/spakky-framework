"""Spakky Saga package - Distributed transaction saga orchestration."""

from spakky.core.application.plugin import Plugin
from spakky.saga.data import AbstractSagaData
from spakky.saga.error import (
    AbstractSpakkySagaError,
    SagaCompensationFailedError,
    SagaFlowDefinitionError,
    SagaParallelMergeConflictError,
)
from spakky.saga.flow import (
    ActionFn,
    CompensateFn,
    FlowItem,
    Parallel,
    SagaDataT,
    SagaFlow,
    SagaStep,
    Transaction,
)
from spakky.saga.result import SagaResult, StepRecord
from spakky.saga.status import SagaStatus
from spakky.saga.strategy import (
    Compensate,
    ErrorStrategy,
    ExponentialBackoff,
    Retry,
    Skip,
)

PLUGIN_NAME = Plugin(name="spakky-saga")
"""Plugin identifier for the Spakky Saga package."""

__all__ = [
    # Data
    "AbstractSagaData",
    # Status
    "SagaStatus",
    # Result
    "SagaResult",
    "StepRecord",
    # Strategy
    "Compensate",
    "Skip",
    "ExponentialBackoff",
    "Retry",
    "ErrorStrategy",
    # Flow
    "SagaStep",
    "Transaction",
    "Parallel",
    "SagaFlow",
    "SagaDataT",
    "ActionFn",
    "CompensateFn",
    "FlowItem",
    # Errors
    "AbstractSpakkySagaError",
    "SagaFlowDefinitionError",
    "SagaCompensationFailedError",
    "SagaParallelMergeConflictError",
    # Plugin
    "PLUGIN_NAME",
]
