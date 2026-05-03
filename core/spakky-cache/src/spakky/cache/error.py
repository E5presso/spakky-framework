"""Error classes for the spakky-cache package."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyCacheError(AbstractSpakkyFrameworkError, ABC):
    """Base class for cache-related errors."""

    ...


class InvalidCacheTTLError(AbstractSpakkyCacheError):
    """Raised when a cache entry is written with an invalid TTL."""

    message = "Cache TTL must be positive"
