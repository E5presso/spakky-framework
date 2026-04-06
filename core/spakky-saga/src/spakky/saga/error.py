"""Spakky Saga error hierarchy."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkySagaError(AbstractSpakkyFrameworkError, ABC):
    """Base class for all spakky-saga errors."""

    ...


class SagaFlowDefinitionError(AbstractSpakkySagaError):
    """Raised when a saga flow definition is invalid (static validation)."""

    message = "Invalid saga flow definition"


class SagaCompensationFailedError(AbstractSpakkySagaError):
    """Raised when compensation fails during saga rollback."""

    message = "Saga compensation failed"


class SagaParallelMergeConflictError(AbstractSpakkySagaError):
    """Raised when parallel steps modify the same field during data merge."""

    message = "Parallel steps modified the same field"


class SagaEngineNotConnectedError(AbstractSpakkySagaError):
    """Raised when execute() is called before the saga engine is connected."""

    message = "Saga engine is not connected"
