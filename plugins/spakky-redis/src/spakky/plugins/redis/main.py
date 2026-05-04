"""Plugin initialization for Redis cache integration."""

from spakky.core.application.application import SpakkyApplication
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.redis.actuator import (
    RedisCacheHealthProbe,
    RedisCacheMetricsInfoContributor,
)
from spakky.plugins.redis.cache import RedisCache
from spakky.plugins.redis.common.config import RedisCacheConfig


def initialize(app: SpakkyApplication) -> None:
    """Register Redis cache configuration and backend pods."""
    app.add(RedisCacheConfig)
    app.add(RedisCache)
    app.add(redis_cache_health_probe)
    app.add(redis_cache_metrics_info_contributor)


@Pod()
def redis_cache_health_probe(
    cache: RedisCache[object],
    config: RedisCacheConfig,
) -> RedisCacheHealthProbe:
    """Create the Redis cache actuator health probe."""
    return RedisCacheHealthProbe(cache, config)


@Pod()
def redis_cache_metrics_info_contributor(
    cache: RedisCache[object],
) -> RedisCacheMetricsInfoContributor:
    """Create the Redis cache actuator metrics info contributor."""
    return RedisCacheMetricsInfoContributor(cache)
