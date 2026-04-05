"""Unit tests for spakky-saga error hierarchy."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError
from spakky.saga.error import (
    AbstractSpakkySagaError,
    SagaCompensationFailedError,
    SagaEngineNotConnectedError,
    SagaFlowDefinitionError,
    SagaParallelMergeConflictError,
)


def test_abstract_spakky_saga_error_subclass_check_expect_abc() -> None:
    """AbstractSpakkySagaError가 ABC 서브클래스인지 검증한다."""
    assert issubclass(AbstractSpakkySagaError, ABC)


def test_abstract_spakky_saga_error_inheritance_expect_framework_error() -> None:
    """AbstractSpakkySagaError가 AbstractSpakkyFrameworkError를 상속하는지 검증한다."""
    assert issubclass(AbstractSpakkySagaError, AbstractSpakkyFrameworkError)


def test_saga_flow_definition_error_inheritance_expect_saga_error() -> None:
    """SagaFlowDefinitionError가 AbstractSpakkySagaError의 서브클래스인지 검증한다."""
    assert issubclass(SagaFlowDefinitionError, AbstractSpakkySagaError)


def test_saga_compensation_failed_error_inheritance_expect_saga_error() -> None:
    """SagaCompensationFailedError가 AbstractSpakkySagaError의 서브클래스인지 검증한다."""
    assert issubclass(SagaCompensationFailedError, AbstractSpakkySagaError)


def test_saga_parallel_merge_conflict_error_inheritance_expect_saga_error() -> None:
    """SagaParallelMergeConflictError가 AbstractSpakkySagaError의 서브클래스인지 검증한다."""
    assert issubclass(SagaParallelMergeConflictError, AbstractSpakkySagaError)


def test_saga_flow_definition_error_message_expect_correct_text() -> None:
    """SagaFlowDefinitionError가 올바른 message 속성을 가지는지 검증한다."""
    assert SagaFlowDefinitionError.message == "Invalid saga flow definition"


def test_saga_compensation_failed_error_message_expect_correct_text() -> None:
    """SagaCompensationFailedError가 올바른 message 속성을 가지는지 검증한다."""
    assert SagaCompensationFailedError.message == "Saga compensation failed"


def test_saga_parallel_merge_conflict_error_message_expect_correct_text() -> None:
    """SagaParallelMergeConflictError가 올바른 message 속성을 가지는지 검증한다."""
    assert (
        SagaParallelMergeConflictError.message
        == "Parallel steps modified the same field"
    )


def test_saga_engine_not_connected_error_inheritance_expect_saga_error() -> None:
    """SagaEngineNotConnectedError가 AbstractSpakkySagaError의 서브클래스인지 검증한다."""
    assert issubclass(SagaEngineNotConnectedError, AbstractSpakkySagaError)


def test_saga_engine_not_connected_error_message_expect_correct_text() -> None:
    """SagaEngineNotConnectedError가 올바른 message 속성을 가지는지 검증한다."""
    assert SagaEngineNotConnectedError.message == "Saga engine is not connected"
