"""Plugin initialization entry point."""

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.logging.aspects.logging_aspect import (
    AsyncLoggingAspect,
    LoggingAspect,
)
from spakky.plugins.logging.config import LoggingConfig
from spakky.plugins.logging.post_processor import LoggingSetupPostProcessor


def initialize(app: SpakkyApplication) -> None:
    """Initialize the spakky-logging plugin.

    Registers the logging configuration, setup post-processor,
    and sync/async logging aspects.

    Args:
        app: The SpakkyApplication instance.
    """
    app.add(LoggingConfig)
    app.add(LoggingSetupPostProcessor)
    app.add(LoggingAspect)
    app.add(AsyncLoggingAspect)
