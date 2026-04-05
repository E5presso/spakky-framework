"""Spakky Saga package - Distributed transaction saga orchestration."""

from spakky.core.application.plugin import Plugin
from spakky.saga.error import (
    AbstractSpakkySagaError,
    SagaCompensationFailedError,
    SagaFlowDefinitionError,
    SagaParallelMergeConflictError,
)

PLUGIN_NAME = Plugin(name="spakky-saga")
"""Plugin identifier for the Spakky Saga package."""

__all__ = [
    # Errors
    "AbstractSpakkySagaError",
    "SagaFlowDefinitionError",
    "SagaCompensationFailedError",
    "SagaParallelMergeConflictError",
    # Plugin
    "PLUGIN_NAME",
]
