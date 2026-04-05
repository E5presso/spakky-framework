"""Saga execution status enumeration."""

from enum import Enum


class SagaStatus(Enum):
    """Represents the current execution status of a saga.

    The status transitions follow this lifecycle:
        STARTED → RUNNING → COMPLETED (success)
        STARTED → RUNNING → COMPENSATING → FAILED (failure with rollback)
        STARTED → RUNNING → TIMED_OUT (timeout exceeded)
    """

    STARTED = "STARTED"
    """Saga has been initiated but not yet running."""

    RUNNING = "RUNNING"
    """Saga steps are being executed."""

    COMPENSATING = "COMPENSATING"
    """A step failed and compensation is in progress."""

    COMPLETED = "COMPLETED"
    """All steps completed successfully."""

    FAILED = "FAILED"
    """Saga failed after compensation."""

    TIMED_OUT = "TIMED_OUT"
    """Saga exceeded its timeout limit."""
