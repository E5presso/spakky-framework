"""Tests for ContextInjectingFilter — injects LogContext into LogRecords."""

import logging

from spakky.plugins.logging.context import LogContext
from spakky.plugins.logging.filters import ContextInjectingFilter


def test_filter_injects_context_values_expect_attributes_on_record() -> None:
    """ContextInjectingFilter가 LogRecord에 LogContext 값을 주입함을 검증한다."""
    LogContext.clear()
    LogContext.bind(request_id="req-abc", user_id="u-123")

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="hello",
        args=None,
        exc_info=None,
    )

    f = ContextInjectingFilter()
    result = f.filter(record)

    assert result is True
    assert record.request_id == "req-abc"  # type: ignore[attr-defined]
    assert record.user_id == "u-123"  # type: ignore[attr-defined]
    assert record.context == {"request_id": "req-abc", "user_id": "u-123"}  # type: ignore[attr-defined]
    LogContext.clear()


def test_filter_empty_context_expect_empty_context_attribute() -> None:
    """LogContext가 비어있을 때 context 속성이 빈 dict임을 검증한다."""
    LogContext.clear()

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="hello",
        args=None,
        exc_info=None,
    )

    f = ContextInjectingFilter()
    f.filter(record)

    assert record.context == {}  # type: ignore[attr-defined]


def test_filter_does_not_overwrite_existing_attribute() -> None:
    """LogRecord에 이미 존재하는 속성은 덮어쓰지 않음을 검증한다."""
    LogContext.clear()
    LogContext.bind(name="from_context")

    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="hello",
        args=None,
        exc_info=None,
    )

    f = ContextInjectingFilter()
    f.filter(record)

    # record.name은 이미 "test.logger"이므로 덮어쓰지 않아야 함
    assert record.name == "test.logger"
    # context dict에는 포함
    assert record.context["name"] == "from_context"  # type: ignore[attr-defined]
    LogContext.clear()


def test_filter_always_returns_true() -> None:
    """ContextInjectingFilter는 항상 True를 반환하여 레코드를 억제하지 않음을 검증한다."""
    LogContext.clear()

    record = logging.LogRecord(
        name="test",
        level=logging.DEBUG,
        pathname="",
        lineno=0,
        msg="msg",
        args=None,
        exc_info=None,
    )

    f = ContextInjectingFilter()

    assert f.filter(record) is True
