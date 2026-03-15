"""Post-processor that configures Python logging on application start.

Reads :class:`LoggingConfig` from the container and applies:

- Root logger level and handler with the selected formatter
- Per-package level overrides
- :class:`ContextInjectingFilter` on the root logger
"""

from __future__ import annotations

import logging

from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor

from spakky.logging.config import LogFormat, LoggingConfig
from spakky.logging.constants import HANDLER_NAME
from spakky.logging.filters import ContextInjectingFilter
from spakky.logging.formatters import (
    SpakkyJsonFormatter,
    SpakkyPrettyFormatter,
    SpakkyTextFormatter,
)


@Order(0)
@Pod()
class LoggingSetupPostProcessor(IPostProcessor, IContainerAware):
    """Post-processor that configures Python logging from LoggingConfig.

    Runs once on the first ``post_process`` call.  Subsequent calls
    are no-ops for the setup logic; the pod itself is returned unchanged.
    """

    __container: IContainer
    __configured: bool

    def __init__(self) -> None:
        super().__init__()
        self.__configured = False

    def set_container(self, container: IContainer) -> None:
        self.__container = container

    def post_process(self, pod: object) -> object:
        """Configure logging on first invocation, then pass through.

        Args:
            pod: The Pod instance being processed.

        Returns:
            The unmodified Pod instance.
        """
        if not self.__configured:
            self.__configured = True
            self._configure()
        return pod

    def _configure(self) -> None:
        """Apply logging configuration from the container."""
        config = self.__container.get(LoggingConfig)
        root = logging.getLogger()

        # Remove any previously installed Spakky handler
        for h in list(root.handlers):
            if getattr(h, "name", None) == HANDLER_NAME:
                root.removeHandler(h)

        # Set root level
        root.setLevel(config.level)

        # Create handler + formatter
        handler = logging.StreamHandler()
        handler.name = HANDLER_NAME

        formatter: logging.Formatter
        match config.format:
            case LogFormat.JSON:
                formatter = SpakkyJsonFormatter(datefmt=config.date_format)
            case LogFormat.PRETTY:
                formatter = SpakkyPrettyFormatter()
            case LogFormat.TEXT:
                formatter = SpakkyTextFormatter(datefmt=config.date_format)
            case _:  # pragma: no cover - exhaustive StrEnum
                raise AssertionError(f"Unknown log format: {config.format}")

        handler.setFormatter(formatter)

        # Inject context filter
        context_filter = ContextInjectingFilter()
        handler.addFilter(context_filter)

        root.addHandler(handler)

        # Per-package level overrides
        for logger_name, level in config.package_levels.items():
            logging.getLogger(logger_name).setLevel(level)
