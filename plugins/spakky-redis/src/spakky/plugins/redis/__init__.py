"""Redis cache backend plugin for Spakky Framework."""

from spakky.core.application.plugin import Plugin

from spakky.plugins.redis.actuator import (
    RedisCacheHealthProbe,
    RedisCacheMetricsInfoContributor,
)
from spakky.plugins.redis.cache import RedisCache
from spakky.plugins.redis.common.config import RedisCacheConfig
from spakky.plugins.redis.error import (
    AbstractSpakkyRedisError,
    RedisCacheLockTimeoutError,
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
    "RedisCacheHealthProbe",
    "RedisCacheLockTimeoutError",
    "RedisCacheMetricsInfoContributor",
    "RedisCacheOperationError",
    "RedisCacheSerializationError",
]
