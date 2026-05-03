"""Plugin initialization for Redis cache integration."""

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.redis.cache import RedisCache
from spakky.plugins.redis.common.config import RedisCacheConfig


def initialize(app: SpakkyApplication) -> None:
    """Register Redis cache configuration and backend pods."""
    app.add(RedisCacheConfig)
    app.add(RedisCache)
