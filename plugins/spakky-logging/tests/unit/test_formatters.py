"""Tests for log formatters — Text, JSON, Pretty."""

import json
import logging
import sys

from spakky.plugins.logging.context import LogContext
from spakky.plugins.logging.filters import ContextInjectingFilter
from spakky.plugins.logging.formatters import (
    SpakkyJsonFormatter,
    SpakkyPrettyFormatter,
    SpakkyTextFormatter,
)


def _make_record(
    msg: str = "test message",
    level: int = logging.INFO,
    name: str = "test.logger",
) -> logging.LogRecord:
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname="",
        lineno=0,
        msg=msg,
        args=None,
        exc_info=None,
    )
    # Inject context like the filter would
    f = ContextInjectingFilter()
    f.filter(record)
    return record


# === SpakkyTextFormatter ===


def test_text_formatter_basic_expect_pipe_separated() -> None:
    """TextFormatter가 파이프로 구분된 한 줄 포맷을 출력함을 검증한다."""
    LogContext.clear()
    fmt = SpakkyTextFormatter()
    record = _make_record()

    output = fmt.format(record)

    assert " | INFO " in output
    assert " | test.logger | " in output
    assert "test message" in output


def test_text_formatter_with_context_expect_context_in_output() -> None:
    """TextFormatter가 LogContext 값을 출력에 포함함을 검증한다."""
    LogContext.clear()
    LogContext.bind(request_id="req-111")
    fmt = SpakkyTextFormatter()
    record = _make_record()

    output = fmt.format(record)

    assert "request_id=req-111" in output
    LogContext.clear()


def test_text_formatter_with_exception_expect_traceback_appended() -> None:
    """TextFormatter가 예외 정보를 포함함을 검증한다."""
    LogContext.clear()
    fmt = SpakkyTextFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="error occurred",
            args=None,
            exc_info=sys.exc_info(),
        )
        ContextInjectingFilter().filter(record)

    output = fmt.format(record)

    assert "ValueError: boom" in output
    assert "error occurred" in output


# === SpakkyJsonFormatter ===


def test_json_formatter_basic_expect_valid_json() -> None:
    """JsonFormatter가 유효한 JSON을 출력함을 검증한다."""
    LogContext.clear()
    fmt = SpakkyJsonFormatter()
    record = _make_record()

    output = fmt.format(record)
    parsed = json.loads(output)

    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test.logger"
    assert parsed["message"] == "test message"
    assert "timestamp" in parsed


def test_json_formatter_with_context_expect_context_fields_in_json() -> None:
    """JsonFormatter가 LogContext 값을 JSON 최상위 필드로 포함함을 검증한다."""
    LogContext.clear()
    LogContext.bind(trace_id="t-999")
    fmt = SpakkyJsonFormatter()
    record = _make_record()

    output = fmt.format(record)
    parsed = json.loads(output)

    assert parsed["trace_id"] == "t-999"
    LogContext.clear()


def test_json_formatter_with_exception_expect_exception_field() -> None:
    """JsonFormatter가 예외 정보를 exception 필드로 포함함을 검증한다."""
    LogContext.clear()
    fmt = SpakkyJsonFormatter()
    try:
        raise RuntimeError("crash")
    except RuntimeError:
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="error",
            args=None,
            exc_info=sys.exc_info(),
        )
        ContextInjectingFilter().filter(record)

    output = fmt.format(record)
    parsed = json.loads(output)

    assert "exception" in parsed
    assert "RuntimeError: crash" in parsed["exception"]


# === SpakkyPrettyFormatter ===


def test_pretty_formatter_basic_expect_ansi_colors() -> None:
    """PrettyFormatter가 ANSI 색상 코드를 포함한 출력을 생성함을 검증한다."""
    LogContext.clear()
    fmt = SpakkyPrettyFormatter()
    record = _make_record()

    output = fmt.format(record)

    # ANSI escape code 포함 확인
    assert "\033[" in output
    assert "test message" in output


def test_pretty_formatter_with_context_expect_context_in_header() -> None:
    """PrettyFormatter가 LogContext 값을 헤더에 포함함을 검증한다."""
    LogContext.clear()
    LogContext.bind(request_id="req-pretty")
    fmt = SpakkyPrettyFormatter()
    record = _make_record()

    output = fmt.format(record)

    assert "request_id=req-pretty" in output
    LogContext.clear()


def test_pretty_formatter_error_level_expect_red_color() -> None:
    """PrettyFormatter가 ERROR 레벨에 빨간색 코드를 사용함을 검증한다."""
    LogContext.clear()
    fmt = SpakkyPrettyFormatter()
    record = _make_record(level=logging.ERROR)

    output = fmt.format(record)

    # Red ANSI code: \033[31m
    assert "\033[31m" in output
    LogContext.clear()


def test_text_formatter_with_stack_info_expect_stack_appended() -> None:
    """TextFormatter가 stack_info를 출력에 포함함을 검증한다."""
    LogContext.clear()
    fmt = SpakkyTextFormatter()
    record = _make_record()
    record.stack_info = "Stack (most recent call last):\n  File ..."

    output = fmt.format(record)

    assert "Stack (most recent call last)" in output


def test_json_formatter_with_stack_info_expect_stack_info_field() -> None:
    """JsonFormatter가 stack_info를 JSON 필드로 포함함을 검증한다."""
    LogContext.clear()
    fmt = SpakkyJsonFormatter()
    record = _make_record()
    record.stack_info = "Stack (most recent call last):\n  File ..."

    output = fmt.format(record)
    parsed = json.loads(output)

    assert "stack_info" in parsed
    assert "Stack (most recent call last)" in parsed["stack_info"]


def test_pretty_formatter_with_exception_expect_traceback_appended() -> None:
    """PrettyFormatter가 예외 정보를 출력에 포함함을 검증한다."""
    LogContext.clear()
    fmt = SpakkyPrettyFormatter()
    try:
        raise RuntimeError("pretty boom")
    except RuntimeError:
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="error occurred",
            args=None,
            exc_info=sys.exc_info(),
        )
        ContextInjectingFilter().filter(record)

    output = fmt.format(record)

    assert "RuntimeError: pretty boom" in output


def test_pretty_formatter_with_stack_info_expect_stack_appended() -> None:
    """PrettyFormatter가 stack_info를 출력에 포함함을 검증한다."""
    LogContext.clear()
    fmt = SpakkyPrettyFormatter()
    record = _make_record()
    record.stack_info = "Stack (most recent call last):\n  File ..."

    output = fmt.format(record)

    assert "Stack (most recent call last)" in output
