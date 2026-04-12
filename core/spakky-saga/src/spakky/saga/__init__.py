"""Spakky Saga package - Distributed transaction saga orchestration."""

from spakky.core.application.plugin import Plugin
from spakky.saga.base import AbstractSaga
from spakky.saga.data import AbstractSagaData
from spakky.saga.error import (
    AbstractSpakkySagaError,
    SagaCompensationFailedError,
    SagaEngineNotConnectedError,
    SagaFlowDefinitionError,
    SagaParallelMergeConflictError,
    SagaStepTimeoutError,
)
from spakky.saga.stereotype import Saga
from spakky.saga.flow import (
    ActionFn,
    CompensateFn,
    FlowItem,
    Parallel,
    SagaDataT,
    SagaFlow,
    SagaStep,
    Transaction,
    parallel,
    saga_flow,
    step,
)
from spakky.saga.engine import run_saga_flow
from spakky.saga.result import SagaResult, StepRecord, StepStatus
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
    # Stereotype
    "Saga",
    # Base
    "AbstractSaga",
    # Data
    "AbstractSagaData",
    # Status
    "SagaStatus",
    # Result
    "SagaResult",
    "StepRecord",
    "StepStatus",
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
    # Engine
    "run_saga_flow",
    # Builder
    "step",
    "parallel",
    "saga_flow",
    # Errors
    "AbstractSpakkySagaError",
    "SagaFlowDefinitionError",
    "SagaCompensationFailedError",
    "SagaParallelMergeConflictError",
    "SagaEngineNotConnectedError",
    "SagaStepTimeoutError",
    # Plugin
    "PLUGIN_NAME",
]
