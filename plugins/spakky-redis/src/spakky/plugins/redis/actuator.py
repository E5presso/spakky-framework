"""Actuator extensions for the Redis cache backend."""

from collections.abc import Mapping

from spakky.actuator import AbstractHealthProbe, ComponentHealthResult, IInfoContributor
from spakky.plugins.redis.cache import RedisCache
from spakky.plugins.redis.common.config import RedisCacheConfig


class RedisCacheHealthProbe(AbstractHealthProbe):
    """Report Redis cache backend reachability."""

    def __init__(self, cache: RedisCache[object], config: RedisCacheConfig) -> None:
        self._cache = cache
        self._config = config

    @property
    def name(self) -> str:
        return "redis-cache"

    def check(self) -> ComponentHealthResult:
        self._cache.ping()
        return ComponentHealthResult.healthy(
            self.name,
            details={
                "database": self._config.db,
                "host": self._config.host,
                "key_prefix": self._config.key_prefix,
                "port": self._config.port,
                "ssl": self._config.use_ssl,
            },
        )


class RedisCacheMetricsInfoContributor(IInfoContributor):
    """Expose Redis cache metrics through actuator info."""

    def __init__(self, cache: RedisCache[object]) -> None:
        self._cache = cache

    @property
    def name(self) -> str:
        return "redis-cache-metrics"

    def contribute_info(self) -> Mapping[str, object]:
        snapshot = self._cache.metrics()
        return {
            "redis_cache": {
                "clears": snapshot.clears,
                "deletes": snapshot.deletes,
                "hits": snapshot.hits,
                "misses": snapshot.misses,
                "stampede_waits": snapshot.stampede_waits,
                "tag_evictions": snapshot.tag_evictions,
                "writes": snapshot.writes,
            }
        }
