"""Error types for domain-level exceptions.

This module defines base error classes for domain logic and validation failures.
"""

from abc import ABC

from spakky.core.error import AbstractSpakkyFrameworkError


class AbstractSpakkyDomainError(AbstractSpakkyFrameworkError, ABC):
    """Base class for all domain-related errors."""

    ...


class AbstractDomainValidationError(AbstractSpakkyDomainError, ABC):
    """Base class for domain validation errors."""

    ...
