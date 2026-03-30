"""Unit tests for tracing error classes."""

from spakky.tracing.error import (
    AbstractSpakkyTracingError,
    InvalidTraceparentError,
)


def test_abstract_tracing_error_is_abstract_expect_concrete_extension() -> None:
    """AbstractSpakkyTracingError가 추상 클래스이며 구체 클래스로 확장 가능함을 검증한다."""

    class ConcreteTracingError(AbstractSpakkyTracingError):
        message = "Test tracing error"

    error = ConcreteTracingError()
    assert error.message == "Test tracing error"
    assert isinstance(error, AbstractSpakkyTracingError)


def test_invalid_traceparent_error_expect_message() -> None:
    """InvalidTraceparentError의 메시지가 올바른지 검증한다."""
    error = InvalidTraceparentError()
    assert error.message == "Invalid traceparent header format"
    assert isinstance(error, AbstractSpakkyTracingError)
