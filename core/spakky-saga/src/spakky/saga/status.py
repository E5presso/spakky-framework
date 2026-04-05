"""Saga execution status."""

from enum import Enum


class SagaStatus(Enum):
    """Saga 실행 상태를 나타내는 열거형."""

    STARTED = "STARTED"
    RUNNING = "RUNNING"
    COMPENSATING = "COMPENSATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
