"""Protocol for logger injection.

This module defines ILoggerAware for Pods that need logger injection.
"""

from abc import abstractmethod
from logging import Logger
from typing import Protocol, runtime_checkable

from spakky.pod.interfaces.aware.aware import IAware


@runtime_checkable
class ILoggerAware(IAware, Protocol):
    """Protocol for Pods requiring logger injection.

    Pods implementing this protocol will have set_logger() called
    during post-processing with the application logger.
    """

    @abstractmethod
    def set_logger(self, logger: Logger) -> None:
        """Inject logger.

        Args:
            logger: The logger instance.
        """
        ...
