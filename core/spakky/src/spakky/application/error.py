"""Error types for application-level exceptions.

This module defines the base error class for all application-related errors.
"""

from abc import ABC

from spakky.core.error import AbstractSpakkyFrameworkError


class AbstractSpakkyApplicationError(AbstractSpakkyFrameworkError, ABC):
    """Base class for all application-level errors."""

    ...
