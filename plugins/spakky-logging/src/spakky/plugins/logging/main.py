"""Plugin initialization entry point."""

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.logging.aspects.logging_aspect import (
    AsyncLoggingAspect,
    LoggingAspect,
)
from spakky.plugins.logging.config import LoggingConfig
from spakky.plugins.logging.log_context_binder import LogContextBinder
from spakky.plugins.logging.post_processor import LoggingSetupPostProcessor


def initialize(app: SpakkyApplication) -> None:
    """Initialize the spakky-logging plugin.

    Registers the logging configuration, setup post-processor,
    sync/async logging aspects, and the log context binder.

    Args:
        app: The SpakkyApplication instance.
    """
    app.add(LoggingConfig)
    app.add(LoggingSetupPostProcessor)
    app.add(LoggingAspect)
    app.add(AsyncLoggingAspect)
    app.add(LogContextBinder)
