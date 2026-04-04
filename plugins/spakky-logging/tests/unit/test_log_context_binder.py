"""Tests for LogContextBinder — Pod adapter for LogContext."""

from spakky.core.logging.interfaces.log_context_binder import ILogContextBinder
from spakky.plugins.logging.context import LogContext
from spakky.plugins.logging.log_context_binder import LogContextBinder


def test_log_context_binder_subclass_expect_implements_interface() -> None:
    """LogContextBinder가 ILogContextBinder의 구현체임을 검증한다."""
    assert issubclass(LogContextBinder, ILogContextBinder)


def test_log_context_binder_bind_expect_values_in_log_context() -> None:
    """bind() 호출이 LogContext에 값을 전달함을 검증한다."""
    LogContext.clear()
    binder = LogContextBinder()

    binder.bind(trace_id="t-123", span_id="s-456")

    assert LogContext.get() == {"trace_id": "t-123", "span_id": "s-456"}
    LogContext.clear()


def test_log_context_binder_unbind_expect_keys_removed_from_log_context() -> None:
    """unbind() 호출이 LogContext에서 키를 제거함을 검증한다."""
    LogContext.clear()
    LogContext.bind(a="1", b="2", c="3")
    binder = LogContextBinder()

    binder.unbind("b")

    assert LogContext.get() == {"a": "1", "c": "3"}
    LogContext.clear()


def test_log_context_binder_unbind_nonexistent_key_expect_no_error() -> None:
    """존재하지 않는 키를 unbind해도 에러가 발생하지 않음을 검증한다."""
    LogContext.clear()
    binder = LogContextBinder()

    binder.unbind("nonexistent")

    assert LogContext.get() == {}
    LogContext.clear()
