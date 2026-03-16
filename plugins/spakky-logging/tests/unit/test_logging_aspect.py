"""Tests for @Logging annotation and LoggingAspect / AsyncLoggingAspect."""

import logging
import time
from logging import Formatter, Logger, LogRecord

import pytest
from spakky.core.aop.aspect import Aspect, AsyncAspect

from spakky.plugins.logging.annotation import Logged, logged
from spakky.plugins.logging.aspects.logging_aspect import (
    AsyncLoggingAspect,
    LoggingAspect,
)


class InMemoryHandler(logging.Handler):
    """Handler that stores formatted log records in memory for assertions."""

    log_records: list[str]

    def __init__(self) -> None:
        super().__init__()
        self.log_records = []

    def emit(self, record: LogRecord) -> None:
        self.log_records.append(self.format(record))


def _setup_logger() -> tuple[Logger, InMemoryHandler]:
    handler = InMemoryHandler()
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(Formatter("[%(levelname)s]: %(message)s"))
    logger: Logger = logging.getLogger("spakky.plugins.logging.aspects.logging_aspect")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    return logger, handler


# === Annotation ===


def test_logging_annotation_exists_expect_true() -> None:
    """@Logging()으로 데코레이트된 함수에서 Logging.exists()가 True를 반환함을 검증한다."""

    class Dummy:
        @logged()
        def method(self) -> None:
            pass

    assert Logged.exists(Dummy.method) is True


def test_logging_annotation_not_exists_expect_false() -> None:
    """데코레이트되지 않은 함수에서 Logging.exists()가 False를 반환함을 검증한다."""

    class Dummy:
        def method(self) -> None:
            pass

    assert Logged.exists(Dummy.method) is False


def test_logging_annotation_custom_fields_expect_values_preserved() -> None:
    """@Logging() 커스텀 필드가 보존됨을 검증한다."""

    class Dummy:
        @logged(
            enable_masking=False,
            masking_keys=["api_key"],
            slow_threshold_ms=500.0,
            max_result_length=50,
            log_args=False,
            log_result=False,
        )
        def method(self) -> None:
            pass

    annotation = Logged.get(Dummy.method)
    assert annotation.enable_masking is False
    assert annotation.masking_keys == ["api_key"]
    assert annotation.slow_threshold_ms == 500.0
    assert annotation.max_result_length == 50
    assert annotation.log_args is False
    assert annotation.log_result is False


# === Sync LoggingAspect ===


def test_logging_aspect_with_masking_expect_password_masked() -> None:
    """LoggingAspect가 password 파라미터를 마스킹 처리하여 로깅함을 검증한다."""
    logger, handler = _setup_logger()

    class Dummy:
        @logged()
        def authenticate(self, username: str, password: str) -> bool:
            return username == "John" and password == "1234"

    aspect = LoggingAspect()
    result = aspect.around(
        joinpoint=Dummy().authenticate,
        username="John",
        password="1234",
    )

    assert result is True
    assert len(handler.log_records) == 1
    assert "password='******'" in handler.log_records[0]
    assert "'1234'" not in handler.log_records[0]

    logger.removeHandler(handler)


def test_logging_aspect_without_masking_expect_password_visible() -> None:
    """LoggingAspect가 마스킹 비활성화 시 password를 그대로 로깅함을 검증한다."""
    logger, handler = _setup_logger()

    class Dummy:
        @logged(enable_masking=False)
        def authenticate(self, username: str, password: str) -> bool:
            return username == "John" and password == "1234"

    aspect = LoggingAspect()
    aspect.around(
        joinpoint=Dummy().authenticate,
        username="John",
        password="1234",
    )

    assert "password='1234'" in handler.log_records[0]

    logger.removeHandler(handler)


def test_logging_aspect_exception_expect_error_logged() -> None:
    """LoggingAspect가 예외 발생 시 ERROR 레벨로 로깅함을 검증한다."""
    logger, handler = _setup_logger()

    class Dummy:
        @logged()
        def fail(self) -> None:
            raise ValueError("boom")

    aspect = LoggingAspect()
    with pytest.raises(ValueError, match="boom"):
        aspect.around(Dummy().fail)

    assert len(handler.log_records) == 1
    assert "[ERROR]" in handler.log_records[0]
    assert "ValueError" in handler.log_records[0]

    logger.removeHandler(handler)


def test_logging_aspect_log_args_false_expect_args_hidden() -> None:
    """LoggingAspect가 log_args=False일 때 인자를 숨김을 검증한다."""
    logger, handler = _setup_logger()

    class Dummy:
        @logged(log_args=False)
        def method(self, value: str) -> str:
            return "ok"

    aspect = LoggingAspect()
    aspect.around(Dummy().method, "secret_data")

    assert "secret_data" not in handler.log_records[0]
    assert "..." in handler.log_records[0]

    logger.removeHandler(handler)


def test_logging_aspect_log_result_false_expect_result_hidden() -> None:
    """LoggingAspect가 log_result=False일 때 반환값을 숨김을 검증한다."""
    logger, handler = _setup_logger()

    class Dummy:
        @logged(log_result=False)
        def method(self) -> str:
            return "sensitive_result"

    aspect = LoggingAspect()
    aspect.around(Dummy().method)

    assert "sensitive_result" not in handler.log_records[0]
    assert "-> ..." in handler.log_records[0]

    logger.removeHandler(handler)


def test_logging_aspect_matches_expect_true_for_annotated() -> None:
    """LoggingAspect가 @Logging 데코레이트된 클래스에 매칭됨을 검증한다."""

    class Dummy:
        @logged()
        def method(self) -> None:
            pass

    class Unmatched:
        def method(self) -> None:
            pass

    aspect = LoggingAspect()
    assert Aspect.get(aspect).matches(Dummy) is True
    assert Aspect.get(aspect).matches(Unmatched) is False


def test_logging_aspect_result_truncation_expect_truncated() -> None:
    """LoggingAspect가 긴 결과를 max_result_length로 잘라서 로깅함을 검증한다."""
    logger, handler = _setup_logger()

    class Dummy:
        @logged(max_result_length=20)
        def long_result(self) -> str:
            return "a" * 100

    aspect = LoggingAspect()
    aspect.around(Dummy().long_result)

    # 결과가 20자+...로 잘려야 함
    log_output = handler.log_records[0]
    assert "a" * 100 not in log_output
    assert "..." in log_output

    logger.removeHandler(handler)


# === Async AsyncLoggingAspect ===


@pytest.mark.asyncio
async def test_async_logging_aspect_with_masking_expect_password_masked() -> None:
    """AsyncLoggingAspect가 password 파라미터를 마스킹 처리하여 로깅함을 검증한다."""
    logger, handler = _setup_logger()

    class Dummy:
        @logged()
        async def authenticate(self, username: str, password: str) -> bool:
            return username == "John" and password == "1234"

    aspect = AsyncLoggingAspect()
    result = await aspect.around_async(
        joinpoint=Dummy().authenticate,
        username="John",
        password="1234",
    )

    assert result is True
    assert "password='******'" in handler.log_records[0]

    logger.removeHandler(handler)


@pytest.mark.asyncio
async def test_async_logging_aspect_without_masking_expect_password_visible() -> None:
    """AsyncLoggingAspect가 마스킹 비활성화 시 password를 그대로 로깅함을 검증한다."""
    logger, handler = _setup_logger()

    class Dummy:
        @logged(enable_masking=False)
        async def authenticate(self, username: str, password: str) -> bool:
            return username == "John" and password == "1234"

    aspect = AsyncLoggingAspect()
    await aspect.around_async(
        joinpoint=Dummy().authenticate,
        username="John",
        password="1234",
    )

    assert "password='1234'" in handler.log_records[0]

    logger.removeHandler(handler)


@pytest.mark.asyncio
async def test_async_logging_aspect_exception_expect_error_logged() -> None:
    """AsyncLoggingAspect가 예외 발생 시 ERROR 레벨로 로깅함을 검증한다."""
    logger, handler = _setup_logger()

    class Dummy:
        @logged()
        async def fail(self) -> None:
            raise ValueError("async boom")

    aspect = AsyncLoggingAspect()
    with pytest.raises(ValueError, match="async boom"):
        await aspect.around_async(Dummy().fail)

    assert "[ERROR]" in handler.log_records[0]
    assert "ValueError" in handler.log_records[0]

    logger.removeHandler(handler)


@pytest.mark.asyncio
async def test_async_logging_aspect_matches_expect_true_for_annotated() -> None:
    """AsyncLoggingAspect가 @Logging 데코레이트된 클래스에 매칭됨을 검증한다."""

    class Dummy:
        @logged()
        async def method(self) -> None:
            pass

    class Unmatched:
        async def method(self) -> None:
            pass

    aspect = AsyncLoggingAspect()
    assert AsyncAspect.get(aspect).matches(Dummy) is True
    assert AsyncAspect.get(aspect).matches(Unmatched) is False


def test_logging_aspect_slow_call_expect_slow_warning() -> None:
    """LoggingAspect가 slow_threshold_ms 초과 시 SLOW 경고를 로깅함을 검증한다."""
    logger, handler = _setup_logger()

    class Dummy:
        @logged(slow_threshold_ms=1.0)
        def slow_method(self) -> str:
            time.sleep(0.01)
            return "done"

    aspect = LoggingAspect()
    aspect.around(Dummy().slow_method)

    assert len(handler.log_records) == 1
    assert "[SLOW]" in handler.log_records[0]

    logger.removeHandler(handler)


@pytest.mark.asyncio
async def test_async_logging_aspect_slow_call_expect_slow_warning() -> None:
    """AsyncLoggingAspect가 slow_threshold_ms 초과 시 SLOW 경고를 로깅함을 검증한다."""
    import asyncio

    logger, handler = _setup_logger()

    class Dummy:
        @logged(slow_threshold_ms=1.0)
        async def slow_method(self) -> str:
            await asyncio.sleep(0.01)
            return "done"

    aspect = AsyncLoggingAspect()
    await aspect.around_async(Dummy().slow_method)

    assert len(handler.log_records) == 1
    assert "[SLOW]" in handler.log_records[0]

    logger.removeHandler(handler)
