"""Error types for infrastructure/port layer.

This module defines base error classes for infrastructure-related failures.
"""

from abc import ABC

from spakky.core.error import AbstractSpakkyFrameworkError


class AbstractSpakkyInfrastructureError(AbstractSpakkyFrameworkError, ABC):
    """Base class for all infrastructure-related errors."""

    ...
