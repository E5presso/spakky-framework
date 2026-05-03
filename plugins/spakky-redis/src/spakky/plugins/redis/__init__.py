"""Redis cache backend plugin for Spakky Framework."""

from spakky.core.application.plugin import Plugin

from spakky.plugins.redis.cache import RedisCache
from spakky.plugins.redis.common.config import RedisCacheConfig
from spakky.plugins.redis.error import (
    AbstractSpakkyRedisError,
    RedisCacheOperationError,
    RedisCacheSerializationError,
)

PLUGIN_NAME = Plugin(name="spakky-redis")
"""Plugin identifier for the Spakky Redis package."""

__all__ = [
    "AbstractSpakkyRedisError",
    "PLUGIN_NAME",
    "RedisCache",
    "RedisCacheConfig",
    "RedisCacheOperationError",
    "RedisCacheSerializationError",
]
