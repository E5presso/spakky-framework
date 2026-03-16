"""Spakky Logging — structured logging system for Spakky Framework.

Public API exports:

- :class:`Logging` — ``@Logging()`` method annotation
- :class:`LoggingAspect` / :class:`AsyncLoggingAspect` — AOP aspects
- :class:`LoggingConfig` — ``@Configuration`` Pod for logging settings
- :class:`LogContext` — ``contextvars``-based context propagation
- :class:`ContextInjectingFilter` — stdlib filter for context injection
- :class:`SpakkyTextFormatter` / :class:`SpakkyJsonFormatter` / :class:`SpakkyPrettyFormatter`
- :class:`LoggingSetupPostProcessor` — auto-configures logging on app start
"""

from spakky.core.application.plugin import Plugin

from spakky.plugins.logging.annotation import Logged, logged
from spakky.plugins.logging.aspects.logging_aspect import (
    AsyncLoggingAspect,
    LoggingAspect,
)
from spakky.plugins.logging.config import LogFormat, LoggingConfig
from spakky.plugins.logging.context import LogContext
from spakky.plugins.logging.filters import ContextInjectingFilter
from spakky.plugins.logging.formatters import (
    SpakkyJsonFormatter,
    SpakkyPrettyFormatter,
    SpakkyTextFormatter,
)
from spakky.plugins.logging.post_processor import LoggingSetupPostProcessor

PLUGIN_NAME = Plugin(name="spakky-logging")

__all__ = [
    "AsyncLoggingAspect",
    "ContextInjectingFilter",
    "LogContext",
    "LogFormat",
    "Logged",
    "logged",
    "LoggingAspect",
    "LoggingConfig",
    "LoggingSetupPostProcessor",
    "SpakkyJsonFormatter",
    "SpakkyPrettyFormatter",
    "SpakkyTextFormatter",
]
