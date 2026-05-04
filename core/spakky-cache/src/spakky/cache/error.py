"""Error classes for the spakky-cache package."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyCacheError(AbstractSpakkyFrameworkError, ABC):
    """Base class for cache-related errors."""

    ...


class InvalidCacheTTLError(AbstractSpakkyCacheError):
    """Raised when a cache entry is written with an invalid TTL."""

    message = "Cache TTL must be positive"


class CacheKeyGenerationError(AbstractSpakkyCacheError):
    """Raised when a cache annotation cannot produce a deterministic key."""

    message = "Cache key generation failed"


class CacheBackendCapabilityError(AbstractSpakkyCacheError):
    """Raised when a cache annotation requires a backend capability."""

    message = "Cache backend does not support the requested capability"
