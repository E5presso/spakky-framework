"""Tests for the Redis cache backend."""

from collections.abc import AsyncIterator, Iterator
from datetime import timedelta

import fakeredis
import pytest
from redis.exceptions import ConnectionError

from spakky.cache import CacheHit, CacheMiss, InvalidCacheTTLError
from spakky.plugins.redis import (
    RedisCache,
    RedisCacheConfig,
    RedisCacheOperationError,
    RedisCacheSerializationError,
)

RedisKey = str | bytes


async def _empty_async_keys() -> AsyncIterator[RedisKey]:
    if False:
        yield "never"


class FailingSyncClient:
    def ping(self) -> bool:
        return True

    def get(self, name: str) -> object:
        raise ConnectionError("get failed")

    def set(self, name: str, value: bytes, *, px: int | None = None) -> object:
        raise ConnectionError("set failed")

    def delete(self, *names: RedisKey) -> object:
        raise ConnectionError("delete failed")

    def scan_iter(self, match: str) -> Iterator[RedisKey]:
        raise ConnectionError("scan failed")


class BadTypeSyncClient:
    def ping(self) -> bool:
        return True

    def get(self, name: str) -> object:
        return "not-bytes"

    def set(self, name: str, value: bytes, *, px: int | None = None) -> object:
        return True

    def delete(self, *names: RedisKey) -> object:
        return "not-int"

    def scan_iter(self, match: str) -> Iterator[RedisKey]:
        return iter(())


class FailingAsyncClient:
    def get(self, name: str) -> object:
        raise ConnectionError("async get failed")

    def set(self, name: str, value: bytes, *, px: int | None = None) -> object:
        raise ConnectionError("async set failed")

    def delete(self, *names: RedisKey) -> object:
        raise ConnectionError("async delete failed")

    def scan_iter(self, match: str) -> AsyncIterator[RedisKey]:
        return _empty_async_keys()


class BadTypeAsyncClient:
    def get(self, name: str) -> object:
        return "not-bytes"

    def set(self, name: str, value: bytes, *, px: int | None = None) -> object:
        return True

    def delete(self, *names: RedisKey) -> object:
        return "not-int"

    def scan_iter(self, match: str) -> AsyncIterator[RedisKey]:
        return _empty_async_keys()


def _cache(
    server: fakeredis.FakeServer, *, prefix: str = "spakky:cache:"
) -> RedisCache[str]:
    config = RedisCacheConfig.model_construct(
        host="localhost",
        port=6379,
        db=0,
        username=None,
        password=None,
        use_ssl=False,
        key_prefix=prefix,
        socket_timeout=5.0,
    )
    sync_client = fakeredis.FakeRedis(server=server)
    async_client = fakeredis.aioredis.FakeRedis(server=server)
    return RedisCache[str](config=config, client=sync_client, async_client=async_client)


def test_shared_redis_server_expect_second_cache_reads_first_cache_value() -> None:
    """같은 Redis 서버를 쓰는 다른 cache instance가 저장 값을 읽는지 검증한다."""
    server = fakeredis.FakeServer()
    writer = _cache(server)
    reader = _cache(server)

    writer.set("user:1", "Ada")
    result = reader.get("user:1")

    assert isinstance(result, CacheHit)
    assert result.value == "Ada"


def test_missing_and_ttl_expiry_expect_typed_miss() -> None:
    """missing key와 TTL 만료가 typed miss로 표현되는지 검증한다."""
    server = fakeredis.FakeServer()
    cache = _cache(server)

    assert isinstance(cache.get("missing"), CacheMiss)

    cache.set("short", "value", ttl=timedelta(milliseconds=1))
    raw_client = fakeredis.FakeRedis(server=server)
    raw_client.expire("spakky:cache:short", 0)

    assert isinstance(cache.get("short"), CacheMiss)


def test_delete_and_clear_expect_only_configured_prefix_removed() -> None:
    """delete와 clear가 configured prefix 범위만 삭제하는지 검증한다."""
    server = fakeredis.FakeServer()
    cache = _cache(server, prefix="app:")
    other = _cache(server, prefix="other:")

    cache.set("a", "1")
    cache.set("b", "2")
    other.set("a", "keep")

    assert cache.delete("a") is True
    cache.clear()

    assert isinstance(cache.get("b"), CacheMiss)
    other_result = other.get("a")
    assert isinstance(other_result, CacheHit)
    assert other_result.value == "keep"

    cache.clear()


async def test_async_contract_expect_shared_value_and_async_clear() -> None:
    """async contract 경로가 Redis backend에서 sync 경로와 호환되는지 검증한다."""
    server = fakeredis.FakeServer()
    cache = _cache(server)

    await cache.set_async("session", "active")
    result = cache.get("session")
    async_result = await cache.get_async("session")

    assert isinstance(result, CacheHit)
    assert result.value == "active"
    assert isinstance(async_result, CacheHit)
    assert async_result.value == "active"

    assert await cache.delete_async("session") is True
    await cache.set_async("session", "active")
    await cache.clear_async()

    assert isinstance(await cache.get_async("session"), CacheMiss)

    await cache.clear_async()


def test_invalid_ttl_expect_core_cache_error() -> None:
    """0 이하 TTL이 core cache TTL error로 실패하는지 검증한다."""
    cache = _cache(fakeredis.FakeServer())

    with pytest.raises(InvalidCacheTTLError):
        cache.set("invalid", "value", ttl=0)


def test_connection_failure_expect_framework_cache_error() -> None:
    """Redis 연결 실패가 framework cache error로 변환되는지 검증한다."""
    config = RedisCacheConfig()
    server = fakeredis.FakeServer()
    server.connected = False

    with pytest.raises(RedisCacheOperationError):
        RedisCache[str](config=config, client=fakeredis.FakeRedis(server=server))


def test_sync_operation_failure_expect_framework_cache_error() -> None:
    """Redis sync operation failure가 framework cache error로 변환되는지 검증한다."""
    cache = RedisCache[str](
        config=RedisCacheConfig(),
        client=FailingSyncClient(),
        async_client=fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer()),
    )

    with pytest.raises(RedisCacheOperationError):
        cache.get("broken")
    with pytest.raises(RedisCacheOperationError):
        cache.set("broken", "value")
    with pytest.raises(RedisCacheOperationError):
        cache.delete("broken")
    with pytest.raises(RedisCacheOperationError):
        cache.clear()


def test_sync_unexpected_response_type_expect_framework_cache_error() -> None:
    """Redis sync response type이 contract와 다르면 framework cache error로 실패한다."""
    cache = RedisCache[str](
        config=RedisCacheConfig(),
        client=BadTypeSyncClient(),
        async_client=fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer()),
    )

    with pytest.raises(RedisCacheOperationError):
        cache.get("bad")
    with pytest.raises(RedisCacheOperationError):
        cache.delete("bad")


async def test_async_operation_failure_expect_framework_cache_error() -> None:
    """Redis async operation failure가 framework cache error로 변환되는지 검증한다."""
    cache = RedisCache[str](
        config=RedisCacheConfig(),
        client=fakeredis.FakeRedis(server=fakeredis.FakeServer()),
        async_client=FailingAsyncClient(),
    )

    with pytest.raises(RedisCacheOperationError):
        await cache.get_async("broken")
    with pytest.raises(RedisCacheOperationError):
        await cache.set_async("broken", "value")
    with pytest.raises(RedisCacheOperationError):
        await cache.delete_async("broken")


async def test_async_unexpected_response_type_expect_framework_cache_error() -> None:
    """Redis async response type이 contract와 다르면 framework cache error로 실패한다."""
    cache = RedisCache[str](
        config=RedisCacheConfig(),
        client=fakeredis.FakeRedis(server=fakeredis.FakeServer()),
        async_client=BadTypeAsyncClient(),
    )

    with pytest.raises(RedisCacheOperationError):
        await cache.get_async("bad")
    with pytest.raises(RedisCacheOperationError):
        await cache.delete_async("bad")


def test_serialization_failure_expect_framework_cache_error() -> None:
    """직렬화 불가능한 값이 framework cache error로 변환되는지 검증한다."""
    cache: RedisCache[object] = RedisCache(
        config=RedisCacheConfig(),
        client=fakeredis.FakeRedis(server=fakeredis.FakeServer()),
    )

    with pytest.raises(RedisCacheSerializationError):
        cache.set("callable", lambda: "not-pickleable")


def test_deserialization_failure_expect_framework_cache_error() -> None:
    """Redis payload 역직렬화 실패가 framework cache error로 변환되는지 검증한다."""
    server = fakeredis.FakeServer()
    cache = _cache(server)
    raw_client = fakeredis.FakeRedis(server=server)
    raw_client.set("spakky:cache:broken", b"not a pickle")

    with pytest.raises(RedisCacheSerializationError):
        cache.get("broken")
