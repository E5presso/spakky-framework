"""Tests for spakky.plugins.logging.__init__ — public API exports and plugin metadata."""

from spakky.core.application.plugin import Plugin

import spakky.plugins.logging as logging_pkg
from spakky.plugins.logging import (
    AsyncLoggingAspect,
    ContextInjectingFilter,
    LogContext,
    LogContextBinder,
    LogFormat,
    Logged,
    LoggingAspect,
    LoggingConfig,
    LoggingSetupPostProcessor,
    SpakkyJsonFormatter,
    SpakkyPrettyFormatter,
    SpakkyTextFormatter,
)


def test_plugin_name_expect_spakky_logging() -> None:
    """PLUGIN_NAME이 'spakky-logging'임을 검증한다."""
    assert logging_pkg.PLUGIN_NAME == Plugin(name="spakky-logging")


def test_all_public_exports_expect_importable() -> None:
    """__all__에 선언된 모든 이름이 실제로 import 가능함을 검증한다."""
    for name in logging_pkg.__all__:
        assert hasattr(logging_pkg, name), f"{name} is in __all__ but not importable"


def test_public_api_classes_expect_correct_types() -> None:
    """공개 API 클래스들이 올바른 타입임을 검증한다."""
    assert isinstance(Logged, type)
    assert isinstance(LoggingAspect, type)
    assert isinstance(AsyncLoggingAspect, type)
    assert isinstance(LoggingConfig, type)
    assert isinstance(LogContext, type)
    assert isinstance(LogContextBinder, type)
    assert isinstance(ContextInjectingFilter, type)
    assert isinstance(SpakkyTextFormatter, type)
    assert isinstance(SpakkyJsonFormatter, type)
    assert isinstance(SpakkyPrettyFormatter, type)
    assert isinstance(LoggingSetupPostProcessor, type)
    assert isinstance(LogFormat, type)
