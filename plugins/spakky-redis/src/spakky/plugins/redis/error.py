"""Error classes for the spakky-redis package."""

from abc import ABC

from spakky.cache.error import AbstractSpakkyCacheError


class AbstractSpakkyRedisError(AbstractSpakkyCacheError, ABC):
    """Base class for Redis cache backend errors."""


class RedisCacheOperationError(AbstractSpakkyRedisError):
    """Raised when a Redis operation fails."""

    message = "Redis cache operation failed"


class RedisCacheSerializationError(AbstractSpakkyRedisError):
    """Raised when a cache value cannot be serialized or deserialized."""

    message = "Redis cache serialization failed"
