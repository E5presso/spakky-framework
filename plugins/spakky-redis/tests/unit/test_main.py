"""Tests for Redis plugin framework integration."""

from collections.abc import AsyncIterator, Iterator
from typing import override

from spakky.cache import ICache
from spakky.cache.aspects.cache_aspect import AsyncCacheAspect, CacheAspect
from spakky.cache.main import initialize as initialize_cache
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.redis.cache import (
    IAsyncRedisClient,
    ISyncRedisClient,
    RedisCache,
    RedisKey,
    RedisKeySet,
)
from spakky.plugins.redis.main import initialize as initialize_redis


class FakeSyncRedisClient(ISyncRedisClient):
    """In-memory sync client boundary for plugin integration tests."""

    @override
    def ping(self) -> None:
        return None

    @override
    def get(self, name: str) -> bytes | None:
        return None

    @override
    def set(self, name: str, value: bytes, *, px: int | None = None) -> None:
        return None

    @override
    def set_if_absent(self, name: str, value: bytes, *, px: int) -> bool:
        return True

    @override
    def delete(self, *names: RedisKey) -> int:
        return 0

    @override
    def add_set_members(self, name: str, *values: RedisKey) -> int:
        return 0

    @override
    def set_members(self, name: str) -> RedisKeySet:
        return set()

    @override
    def scan_iter(self, match: str) -> Iterator[RedisKey]:
        return iter(())


async def _empty_async_redis_keys() -> AsyncIterator[RedisKey]:
    if False:
        yield ""


class FakeAsyncRedisClient(IAsyncRedisClient):
    """In-memory async client boundary for plugin integration tests."""

    @override
    async def get(self, name: str) -> bytes | None:
        return None

    @override
    async def set(
        self,
        name: str,
        value: bytes,
        *,
        px: int | None = None,
    ) -> None:
        return None

    @override
    async def set_if_absent(self, name: str, value: bytes, *, px: int) -> bool:
        return True

    @override
    async def delete(self, *names: RedisKey) -> int:
        return 0

    @override
    async def add_set_members(self, name: str, *values: RedisKey) -> int:
        return 0

    @override
    async def set_members(self, name: str) -> RedisKeySet:
        return set()

    @override
    def scan_iter(self, match: str) -> AsyncIterator[RedisKey]:
        return _empty_async_redis_keys()


@Pod()
def sync_redis_client() -> ISyncRedisClient:
    """Provide a fake sync Redis client for RedisCache construction."""
    return FakeSyncRedisClient()


@Pod()
def async_redis_client() -> IAsyncRedisClient:
    """Provide a fake async Redis client for RedisCache construction."""
    return FakeAsyncRedisClient()


def test_redis_plugin_provides_cache_backend_for_cache_aspects() -> None:
    """spakky-cache + spakky-redis resolves ICache and cache aspects."""
    context = ApplicationContext()
    app = SpakkyApplication(context)
    initialize_cache(app)
    initialize_redis(app)
    app.add(sync_redis_client)
    app.add(async_redis_client)

    app.start()
    try:
        assert isinstance(context.get(ICache), RedisCache)
        assert isinstance(context.get(CacheAspect), CacheAspect)
        assert isinstance(context.get(AsyncCacheAspect), AsyncCacheAspect)
    finally:
        app.stop()
