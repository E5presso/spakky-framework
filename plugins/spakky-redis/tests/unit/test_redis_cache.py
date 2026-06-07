"""Tests for the Redis cache backend."""

from collections.abc import AsyncIterator, Iterator, Mapping, Set
from datetime import timedelta
import pickle

import fakeredis
import pytest
from redis.exceptions import RedisError
from typing import override

import spakky.plugins.redis.cache as redis_cache_module
from spakky.cache import CacheHit, CacheMiss, InvalidCacheTTLError
from spakky.plugins.redis import (
    RedisCache,
    RedisCacheConfig,
    RedisCacheHealthProbe,
    RedisCacheLockTimeoutError,
    RedisCacheMetricsInfoContributor,
    RedisCacheOperationError,
    RedisCacheSerializationError,
)
from spakky.plugins.redis.cache import (
    IRawAsyncRedisClient,
    IRawSyncRedisClient,
    IAsyncRedisClient,
    ISyncRedisClient,
    AsyncRedisAdapter,
    RedisRawAsyncClient,
    RedisRawSyncClient,
    SyncRedisAdapter,
)

RedisKey = str | bytes


async def _empty_async_keys() -> AsyncIterator[RedisKey]:
    if False:
        yield "never"


class FailingSyncClient(ISyncRedisClient):
    @override
    def ping(self) -> None:
        return None

    @override
    def get(self, name: str) -> bytes | None:
        raise RedisCacheOperationError

    @override
    def set(self, name: str, value: bytes, *, px: int | None = None) -> None:
        raise RedisCacheOperationError

    @override
    def set_if_absent(self, name: str, value: bytes, *, px: int) -> bool:
        raise RedisCacheOperationError

    @override
    def delete(self, *names: RedisKey) -> int:
        raise RedisCacheOperationError

    @override
    def add_set_members(self, name: str, *values: RedisKey) -> int:
        raise RedisCacheOperationError

    @override
    def set_members(self, name: str) -> Set[RedisKey]:
        raise RedisCacheOperationError

    @override
    def scan_iter(self, match: str) -> Iterator[RedisKey]:
        raise RedisCacheOperationError


class BadTypeSyncClient(IRawSyncRedisClient):
    @override
    def ping(self) -> object:
        return True

    @override
    def get(self, name: str) -> object:
        return "not-bytes"

    @override
    def set(self, name: str, value: bytes, *, px: int | None = None) -> object:
        return True

    @override
    def set_if_absent(self, name: str, value: bytes, *, px: int) -> object:
        return True

    @override
    def delete(self, *names: RedisKey) -> object:
        return "not-int"

    @override
    def add_set_members(self, name: str, *values: RedisKey) -> object:
        return "not-int"

    @override
    def set_members(self, name: str) -> object:
        return "not-set"

    @override
    def scan_iter(self, match: str) -> Iterator[RedisKey]:
        return iter(())


class NoneSetIfAbsentSyncClient(BadTypeSyncClient):
    @override
    def set_if_absent(self, name: str, value: bytes, *, px: int) -> object:
        return None


class BadSetIfAbsentSyncClient(BadTypeSyncClient):
    @override
    def set_if_absent(self, name: str, value: bytes, *, px: int) -> object:
        return "not-bool"


class FailingAsyncClient(IAsyncRedisClient):
    @override
    async def get(self, name: str) -> bytes | None:
        raise RedisCacheOperationError

    @override
    async def set(self, name: str, value: bytes, *, px: int | None = None) -> None:
        raise RedisCacheOperationError

    @override
    async def set_if_absent(self, name: str, value: bytes, *, px: int) -> bool:
        raise RedisCacheOperationError

    @override
    async def delete(self, *names: RedisKey) -> int:
        raise RedisCacheOperationError

    @override
    async def add_set_members(self, name: str, *values: RedisKey) -> int:
        raise RedisCacheOperationError

    @override
    async def set_members(self, name: str) -> Set[RedisKey]:
        raise RedisCacheOperationError

    @override
    def scan_iter(self, match: str) -> AsyncIterator[RedisKey]:
        return _empty_async_keys()


class BadTypeAsyncClient(IRawAsyncRedisClient):
    @override
    async def get(self, name: str) -> object:
        return "not-bytes"

    @override
    async def set(self, name: str, value: bytes, *, px: int | None = None) -> object:
        return True

    @override
    async def set_if_absent(self, name: str, value: bytes, *, px: int) -> object:
        return True

    @override
    async def delete(self, *names: RedisKey) -> object:
        return "not-int"

    @override
    async def add_set_members(self, name: str, *values: RedisKey) -> object:
        return "not-int"

    @override
    async def set_members(self, name: str) -> object:
        return "not-set"

    @override
    def scan_iter(self, match: str) -> AsyncIterator[RedisKey]:
        return _empty_async_keys()


class NoneSetIfAbsentAsyncClient(BadTypeAsyncClient):
    @override
    async def set_if_absent(self, name: str, value: bytes, *, px: int) -> object:
        return None


class BadSetIfAbsentAsyncClient(BadTypeAsyncClient):
    @override
    async def set_if_absent(self, name: str, value: bytes, *, px: int) -> object:
        return "not-bool"


class RedisErrorSyncClient(IRawSyncRedisClient):
    @override
    def ping(self) -> object:
        return True

    @override
    def get(self, name: str) -> object:
        raise RedisError

    @override
    def set(self, name: str, value: bytes, *, px: int | None = None) -> object:
        raise RedisError

    @override
    def set_if_absent(self, name: str, value: bytes, *, px: int) -> object:
        raise RedisError

    @override
    def delete(self, *names: RedisKey) -> object:
        raise RedisError

    @override
    def add_set_members(self, name: str, *values: RedisKey) -> object:
        raise RedisError

    @override
    def set_members(self, name: str) -> object:
        raise RedisError

    @override
    def scan_iter(self, match: str) -> Iterator[RedisKey]:
        raise RedisError


class RedisErrorAsyncClient(IRawAsyncRedisClient):
    @override
    async def get(self, name: str) -> object:
        raise RedisError

    @override
    async def set(self, name: str, value: bytes, *, px: int | None = None) -> object:
        raise RedisError

    @override
    async def set_if_absent(self, name: str, value: bytes, *, px: int) -> object:
        raise RedisError

    @override
    async def delete(self, *names: RedisKey) -> object:
        raise RedisError

    @override
    async def add_set_members(self, name: str, *values: RedisKey) -> object:
        raise RedisError

    @override
    async def set_members(self, name: str) -> object:
        raise RedisError

    @override
    def scan_iter(self, match: str) -> AsyncIterator[RedisKey]:
        raise RedisError


class ContendedSyncClient(ISyncRedisClient):
    def __init__(self) -> None:
        self.get_calls = 0

    @override
    def ping(self) -> None:
        return None

    @override
    def get(self, name: str) -> bytes | None:
        self.get_calls += 1
        if self.get_calls <= 2:
            return None
        return pickle.dumps("ready", protocol=pickle.HIGHEST_PROTOCOL)

    @override
    def set(self, name: str, value: bytes, *, px: int | None = None) -> None:
        return None

    @override
    def set_if_absent(self, name: str, value: bytes, *, px: int) -> bool:
        return False

    @override
    def delete(self, *names: RedisKey) -> int:
        return 0

    @override
    def add_set_members(self, name: str, *values: RedisKey) -> int:
        return 0

    @override
    def set_members(self, name: str) -> Set[RedisKey]:
        return set()

    @override
    def scan_iter(self, match: str) -> Iterator[RedisKey]:
        return iter(())


class TimeoutSyncClient(ContendedSyncClient):
    @override
    def get(self, name: str) -> bytes | None:
        return None


class ReacquirableSyncClient(ContendedSyncClient):
    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, bytes] = {}
        self.lock_attempts = 0

    @override
    def get(self, name: str) -> bytes | None:
        return self.values.get(name)

    @override
    def set(self, name: str, value: bytes, *, px: int | None = None) -> None:
        self.values[name] = value

    @override
    def set_if_absent(self, name: str, value: bytes, *, px: int) -> bool:
        self.lock_attempts += 1
        return self.lock_attempts > 1

    @override
    def add_set_members(self, name: str, *values: RedisKey) -> int:
        return len(values)


class ContendedAsyncClient(IAsyncRedisClient):
    def __init__(self) -> None:
        self.get_calls = 0

    @override
    async def get(self, name: str) -> bytes | None:
        self.get_calls += 1
        if self.get_calls <= 2:
            return None
        return pickle.dumps("ready", protocol=pickle.HIGHEST_PROTOCOL)

    @override
    async def set(self, name: str, value: bytes, *, px: int | None = None) -> None:
        return None

    @override
    async def set_if_absent(self, name: str, value: bytes, *, px: int) -> bool:
        return False

    @override
    async def delete(self, *names: RedisKey) -> int:
        return 0

    @override
    async def add_set_members(self, name: str, *values: RedisKey) -> int:
        return 0

    @override
    async def set_members(self, name: str) -> Set[RedisKey]:
        return set()

    @override
    def scan_iter(self, match: str) -> AsyncIterator[RedisKey]:
        return _empty_async_keys()


class TimeoutAsyncClient(ContendedAsyncClient):
    @override
    async def get(self, name: str) -> bytes | None:
        return None


class ReacquirableAsyncClient(ContendedAsyncClient):
    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, bytes] = {}
        self.lock_attempts = 0

    @override
    async def get(self, name: str) -> bytes | None:
        return self.values.get(name)

    @override
    async def set(self, name: str, value: bytes, *, px: int | None = None) -> None:
        self.values[name] = value

    @override
    async def set_if_absent(self, name: str, value: bytes, *, px: int) -> bool:
        self.lock_attempts += 1
        return self.lock_attempts > 1

    @override
    async def add_set_members(self, name: str, *values: RedisKey) -> int:
        return len(values)


def _cache(
    server: fakeredis.FakeServer, *, prefix: str = "spakky:cache:"
) -> RedisCache[object]:
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
    return RedisCache[object](
        config=config,
        client=SyncRedisAdapter(RedisRawSyncClient(sync_client)),
        async_client=AsyncRedisAdapter(RedisRawAsyncClient(async_client)),
    )


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


def test_ttl_float_expect_redis_millisecond_expiry() -> None:
    """float TTL이 Redis millisecond expiry로 변환되는지 검증한다."""
    server = fakeredis.FakeServer()
    cache = _cache(server)
    raw_client = fakeredis.FakeRedis(server=server)

    cache.set("short", "value", ttl=1.25)

    ttl_ms = raw_client.pttl("spakky:cache:short")
    assert isinstance(ttl_ms, int)
    assert 0 < ttl_ms <= 1250


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


def test_delete_missing_expect_false_and_delete_metric_unchanged() -> None:
    """delete miss가 False를 반환하고 delete metric을 증가시키지 않는지 검증한다."""
    cache = _cache(fakeredis.FakeServer())

    deleted = cache.delete("missing")

    assert deleted is False
    assert cache.metrics().deletes == 0


def test_tagged_entries_expect_tag_eviction_removes_matching_values() -> None:
    """tag evict가 같은 tag로 묶인 cache entry만 제거하는지 검증한다."""
    server = fakeredis.FakeServer()
    cache = _cache(server, prefix="app:")
    other = _cache(server, prefix="other:")

    cache.set_with_tags("profile:1", "Ada", tags=("profile",))
    cache.set_with_tags("profile:2", "Grace", tags=("profile",))
    cache.set_with_tags("settings:1", "dark", tags=("settings",))
    other.set_with_tags("profile:1", "Keep", tags=("profile",))

    deleted = cache.evict_tags("profile")

    assert deleted == 3
    assert isinstance(cache.get("profile:1"), CacheMiss)
    assert isinstance(cache.get("profile:2"), CacheMiss)
    assert isinstance(cache.get("settings:1"), CacheHit)
    other_result = other.get("profile:1")
    assert isinstance(other_result, CacheHit)
    assert other_result.value == "Keep"


def test_evict_tags_without_matching_entries_expect_zero() -> None:
    """tag 인자가 없으면 tag eviction이 no-op으로 끝나는지 검증한다."""
    cache = _cache(fakeredis.FakeServer())

    deleted = cache.evict_tags()

    assert deleted == 0
    assert cache.metrics().tag_evictions == 0


def test_get_or_set_expect_factory_runs_only_on_miss_and_metrics_recorded() -> None:
    """get_or_set이 miss에서만 값을 생성하고 metrics를 누적하는지 검증한다."""
    cache = _cache(fakeredis.FakeServer())
    calls = 0

    def factory() -> str:
        nonlocal calls
        calls += 1
        return f"value:{calls}"

    first = cache.get_or_set("expensive", factory, tags=("expensive",))
    second = cache.get_or_set("expensive", factory, tags=("expensive",))
    snapshot = cache.metrics()

    assert first == second == "value:1"
    assert calls == 1
    assert snapshot.hits >= 1
    assert snapshot.misses >= 1
    assert snapshot.writes == 1


def test_write_policies_expect_origin_and_cache_updated_in_order() -> None:
    """write-through/write-behind 정책이 origin writer와 cache update를 수행하는지 검증한다."""
    cache = _cache(fakeredis.FakeServer())
    events: list[str] = []

    def through_writer(value: object) -> None:
        events.append(f"through:{value}")
        assert isinstance(cache.get("through"), CacheMiss)

    def behind_writer(value: object) -> None:
        events.append(f"behind:{value}")
        assert isinstance(cache.get("behind"), CacheHit)

    cache.write_through("through", "A", through_writer, tags=("policy",))
    cache.write_behind("behind", "B", behind_writer, tags=("policy",))

    assert events == ["through:A", "behind:B"]
    assert isinstance(cache.get("through"), CacheHit)
    assert isinstance(cache.get("behind"), CacheHit)


def test_actuator_extensions_expect_health_and_metrics_payload() -> None:
    """Redis actuator extension이 backend health와 metrics를 노출하는지 검증한다."""
    cache = _cache(fakeredis.FakeServer())
    cache.set("profile:1", "Ada")
    assert isinstance(cache.get("profile:1"), CacheHit)
    config = RedisCacheConfig.model_construct(
        host="localhost",
        port=6379,
        db=0,
        username=None,
        password=None,
        use_ssl=False,
        key_prefix="spakky:cache:",
        socket_timeout=5.0,
    )
    probe = RedisCacheHealthProbe(cache, config)
    contributor = RedisCacheMetricsInfoContributor(cache)

    health = probe.check()
    info = contributor.contribute_info()

    assert health.name == "redis-cache"
    assert contributor.name == "redis-cache-metrics"
    assert health.details["key_prefix"] == "spakky:cache:"
    redis_info = info["redis_cache"]
    assert isinstance(redis_info, Mapping)
    assert redis_info["hits"] == 1
    assert redis_info["writes"] == 1


def test_get_or_set_contention_expect_waits_for_peer_value() -> None:
    """get_or_set lock contention 시 peer가 채운 값을 대기 후 반환하는지 검증한다."""
    client = ContendedSyncClient()
    cache = RedisCache[str](
        config=RedisCacheConfig(),
        client=client,
        async_client=AsyncRedisAdapter(
            RedisRawAsyncClient(
                fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer())
            )
        ),
    )

    value = cache.get_or_set("item", lambda: "unused")

    assert value == "ready"
    assert cache.metrics().stampede_waits == 1


def test_get_or_set_contention_expect_reacquires_abandoned_lock() -> None:
    """A waiter reacquires ownership when no peer ever publishes the value."""
    client = ReacquirableSyncClient()
    cache = RedisCache[str](
        config=RedisCacheConfig(),
        client=client,
        async_client=AsyncRedisAdapter(
            RedisRawAsyncClient(
                fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer())
            )
        ),
    )
    calls = 0

    def factory() -> str:
        nonlocal calls
        calls += 1
        return "recovered"

    value = cache.get_or_set("item", factory, tags=("items",))

    assert value == "recovered"
    assert calls == 1
    assert client.lock_attempts == 2
    assert cache.metrics().stampede_waits == 1


def test_get_or_set_contention_timeout_expect_cache_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_or_set contention timeout이 framework cache error로 노출되는지 검증한다."""
    times = iter((0.0, 31.0))
    client = TimeoutSyncClient()
    cache = RedisCache[str](
        config=RedisCacheConfig(),
        client=client,
        async_client=AsyncRedisAdapter(
            RedisRawAsyncClient(
                fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer())
            )
        ),
    )

    def monotonic() -> float:
        return next(times)

    monkeypatch.setattr(redis_cache_module, "monotonic", monotonic)
    monkeypatch.setattr(redis_cache_module, "sleep", lambda seconds: None)

    with pytest.raises(RedisCacheLockTimeoutError):
        cache.get_or_set("item", lambda: "unused")

    assert cache.metrics().stampede_waits == 1


def test_extended_sync_adapter_failures_expect_framework_cache_error() -> None:
    """extended sync adapter operation 실패가 framework cache error로 변환되는지 검증한다."""
    bad = SyncRedisAdapter(BadTypeSyncClient())
    none_lock = SyncRedisAdapter(NoneSetIfAbsentSyncClient())
    bad_lock = SyncRedisAdapter(BadSetIfAbsentSyncClient())
    broken = SyncRedisAdapter(RedisErrorSyncClient())

    assert bad.set_if_absent("lock", b"1", px=1) is True
    assert none_lock.set_if_absent("lock", b"1", px=1) is False
    with pytest.raises(RedisCacheOperationError):
        bad_lock.set_if_absent("lock", b"1", px=1)
    with pytest.raises(RedisCacheOperationError):
        bad.add_set_members("tag", "key")
    with pytest.raises(RedisCacheOperationError):
        bad.set_members("tag")
    with pytest.raises(RedisCacheOperationError):
        broken.set_if_absent("lock", b"1", px=1)
    with pytest.raises(RedisCacheOperationError):
        broken.add_set_members("tag", "key")
    with pytest.raises(RedisCacheOperationError):
        broken.set_members("tag")


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


async def test_async_delete_missing_expect_false_and_delete_metric_unchanged() -> None:
    """async delete miss가 False를 반환하고 delete metric을 증가시키지 않는다."""
    cache = _cache(fakeredis.FakeServer())

    deleted = await cache.delete_async("missing")

    assert deleted is False
    assert cache.metrics().deletes == 0


async def test_async_clear_expect_only_configured_prefix_removed() -> None:
    """async clear가 configured prefix 범위만 삭제하는지 검증한다."""
    server = fakeredis.FakeServer()
    cache = _cache(server, prefix="app:")
    other = _cache(server, prefix="other:")

    await cache.set_async("a", "1")
    await cache.set_async("b", "2")
    await other.set_async("a", "keep")

    await cache.clear_async()

    assert isinstance(await cache.get_async("a"), CacheMiss)
    assert isinstance(await cache.get_async("b"), CacheMiss)
    other_result = await other.get_async("a")
    assert isinstance(other_result, CacheHit)
    assert other_result.value == "keep"


async def test_async_tagged_entries_expect_tag_eviction_removes_matching_values() -> (
    None
):
    """async tag evict가 같은 tag로 묶인 cache entry만 제거하는지 검증한다."""
    server = fakeredis.FakeServer()
    cache = _cache(server, prefix="app:")
    other = _cache(server, prefix="other:")

    await cache.set_with_tags_async("profile:1", "Ada", tags=("profile",))
    await cache.set_with_tags_async("profile:2", "Grace", tags=("profile",))
    await cache.set_with_tags_async("settings:1", "dark", tags=("settings",))
    await other.set_with_tags_async("profile:1", "Keep", tags=("profile",))

    deleted = await cache.evict_tags_async("profile")

    assert deleted == 3
    assert isinstance(await cache.get_async("profile:1"), CacheMiss)
    assert isinstance(await cache.get_async("profile:2"), CacheMiss)
    assert isinstance(await cache.get_async("settings:1"), CacheHit)
    other_result = await other.get_async("profile:1")
    assert isinstance(other_result, CacheHit)
    assert other_result.value == "Keep"


async def test_async_evict_tags_without_matching_entries_expect_zero() -> None:
    """async tag eviction도 tag 인자가 없으면 no-op으로 끝난다."""
    cache = _cache(fakeredis.FakeServer())

    deleted = await cache.evict_tags_async()

    assert deleted == 0
    assert cache.metrics().tag_evictions == 0


async def test_async_get_or_set_expect_factory_runs_only_on_miss() -> None:
    """async get_or_set이 miss에서만 값을 생성하는지 검증한다."""
    cache = _cache(fakeredis.FakeServer())
    calls = 0

    async def factory() -> str:
        nonlocal calls
        calls += 1
        return f"value:{calls}"

    first = await cache.get_or_set_async("expensive", factory, tags=("expensive",))
    second = await cache.get_or_set_async("expensive", factory, tags=("expensive",))

    assert first == second == "value:1"
    assert calls == 1


async def test_async_write_policies_expect_origin_and_cache_updated_in_order() -> None:
    """async write-through/write-behind 정책이 origin writer와 cache update를 수행한다."""
    cache = _cache(fakeredis.FakeServer())
    events: list[str] = []

    async def through_writer(value: object) -> None:
        events.append(f"through:{value}")
        assert isinstance(await cache.get_async("through"), CacheMiss)

    async def behind_writer(value: object) -> None:
        events.append(f"behind:{value}")
        assert isinstance(await cache.get_async("behind"), CacheHit)

    await cache.write_through_async("through", "A", through_writer, tags=("policy",))
    await cache.write_behind_async("behind", "B", behind_writer, tags=("policy",))

    assert events == ["through:A", "behind:B"]
    assert isinstance(await cache.get_async("through"), CacheHit)
    assert isinstance(await cache.get_async("behind"), CacheHit)


async def test_async_get_or_set_contention_expect_waits_for_peer_value() -> None:
    """async get_or_set lock contention 시 peer가 채운 값을 대기 후 반환하는지 검증한다."""
    client = ContendedAsyncClient()
    cache = RedisCache[str](
        config=RedisCacheConfig(),
        client=SyncRedisAdapter(
            RedisRawSyncClient(fakeredis.FakeRedis(server=fakeredis.FakeServer()))
        ),
        async_client=client,
    )

    async def factory() -> str:
        return "unused"

    value = await cache.get_or_set_async("item", factory)

    assert value == "ready"
    assert cache.metrics().stampede_waits == 1


async def test_async_get_or_set_contention_expect_reacquires_abandoned_lock() -> None:
    """A waiter reacquires ownership when no peer ever publishes the value."""
    client = ReacquirableAsyncClient()
    cache = RedisCache[str](
        config=RedisCacheConfig(),
        client=SyncRedisAdapter(
            RedisRawSyncClient(fakeredis.FakeRedis(server=fakeredis.FakeServer()))
        ),
        async_client=client,
    )
    calls = 0

    async def factory() -> str:
        nonlocal calls
        calls += 1
        return "recovered"

    value = await cache.get_or_set_async("item", factory, tags=("items",))

    assert value == "recovered"
    assert calls == 1
    assert client.lock_attempts == 2
    assert cache.metrics().stampede_waits == 1


async def test_async_get_or_set_contention_timeout_expect_cache_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """async get_or_set contention timeout이 framework cache error로 노출된다."""
    times = iter((0.0, 31.0))
    client = TimeoutAsyncClient()
    cache = RedisCache[str](
        config=RedisCacheConfig(),
        client=SyncRedisAdapter(
            RedisRawSyncClient(fakeredis.FakeRedis(server=fakeredis.FakeServer()))
        ),
        async_client=client,
    )

    def monotonic() -> float:
        return next(times)

    async def sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(redis_cache_module, "monotonic", monotonic)
    monkeypatch.setattr(redis_cache_module, "async_sleep", sleep)

    async def factory() -> str:
        return "unused"

    with pytest.raises(RedisCacheLockTimeoutError):
        await cache.get_or_set_async("item", factory)

    assert cache.metrics().stampede_waits == 1


async def test_extended_async_adapter_failures_expect_framework_cache_error() -> None:
    """extended async adapter operation 실패가 framework cache error로 변환되는지 검증한다."""
    bad = AsyncRedisAdapter(BadTypeAsyncClient())
    none_lock = AsyncRedisAdapter(NoneSetIfAbsentAsyncClient())
    bad_lock = AsyncRedisAdapter(BadSetIfAbsentAsyncClient())
    broken = AsyncRedisAdapter(RedisErrorAsyncClient())

    assert await bad.set_if_absent("lock", b"1", px=1) is True
    assert await none_lock.set_if_absent("lock", b"1", px=1) is False
    with pytest.raises(RedisCacheOperationError):
        await bad_lock.set_if_absent("lock", b"1", px=1)
    with pytest.raises(RedisCacheOperationError):
        await bad.add_set_members("tag", "key")
    with pytest.raises(RedisCacheOperationError):
        await bad.set_members("tag")
    with pytest.raises(RedisCacheOperationError):
        await broken.set_if_absent("lock", b"1", px=1)
    with pytest.raises(RedisCacheOperationError):
        await broken.add_set_members("tag", "key")
    with pytest.raises(RedisCacheOperationError):
        await broken.set_members("tag")


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
        RedisCache[str](
            config=config,
            client=SyncRedisAdapter(
                RedisRawSyncClient(fakeredis.FakeRedis(server=server))
            ),
        )


def test_sync_operation_failure_expect_framework_cache_error() -> None:
    """Redis sync operation failure가 framework cache error로 변환되는지 검증한다."""
    cache = RedisCache[str](
        config=RedisCacheConfig(),
        client=FailingSyncClient(),
        async_client=AsyncRedisAdapter(
            RedisRawAsyncClient(
                fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer())
            )
        ),
    )

    with pytest.raises(RedisCacheOperationError):
        cache.get("broken")
    with pytest.raises(RedisCacheOperationError):
        cache.set("broken", "value")
    with pytest.raises(RedisCacheOperationError):
        cache.delete("broken")
    with pytest.raises(RedisCacheOperationError):
        cache.clear()


def test_sync_redis_error_expect_framework_cache_error() -> None:
    """Raw RedisError가 sync adapter에서 framework cache error로 변환되는지 검증한다."""
    cache = RedisCache[str](
        config=RedisCacheConfig(),
        client=SyncRedisAdapter(RedisErrorSyncClient()),
        async_client=AsyncRedisAdapter(
            RedisRawAsyncClient(
                fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer())
            )
        ),
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
        client=SyncRedisAdapter(BadTypeSyncClient()),
        async_client=AsyncRedisAdapter(
            RedisRawAsyncClient(
                fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer())
            )
        ),
    )

    with pytest.raises(RedisCacheOperationError):
        cache.get("bad")
    with pytest.raises(RedisCacheOperationError):
        cache.delete("bad")


async def test_async_operation_failure_expect_framework_cache_error() -> None:
    """Redis async operation failure가 framework cache error로 변환되는지 검증한다."""
    cache = RedisCache[str](
        config=RedisCacheConfig(),
        client=SyncRedisAdapter(
            RedisRawSyncClient(fakeredis.FakeRedis(server=fakeredis.FakeServer()))
        ),
        async_client=FailingAsyncClient(),
    )

    with pytest.raises(RedisCacheOperationError):
        await cache.get_async("broken")
    with pytest.raises(RedisCacheOperationError):
        await cache.set_async("broken", "value")
    with pytest.raises(RedisCacheOperationError):
        await cache.delete_async("broken")


async def test_async_redis_error_expect_framework_cache_error() -> None:
    """Raw RedisError가 async adapter에서 framework cache error로 변환되는지 검증한다."""
    cache = RedisCache[str](
        config=RedisCacheConfig(),
        client=SyncRedisAdapter(
            RedisRawSyncClient(fakeredis.FakeRedis(server=fakeredis.FakeServer()))
        ),
        async_client=AsyncRedisAdapter(RedisErrorAsyncClient()),
    )

    with pytest.raises(RedisCacheOperationError):
        await cache.get_async("broken")
    with pytest.raises(RedisCacheOperationError):
        await cache.set_async("broken", "value")
    with pytest.raises(RedisCacheOperationError):
        await cache.delete_async("broken")
    with pytest.raises(RedisCacheOperationError):
        await cache.clear_async()


async def test_async_unexpected_response_type_expect_framework_cache_error() -> None:
    """Redis async response type이 contract와 다르면 framework cache error로 실패한다."""
    cache = RedisCache[str](
        config=RedisCacheConfig(),
        client=SyncRedisAdapter(
            RedisRawSyncClient(fakeredis.FakeRedis(server=fakeredis.FakeServer()))
        ),
        async_client=AsyncRedisAdapter(BadTypeAsyncClient()),
    )

    with pytest.raises(RedisCacheOperationError):
        await cache.get_async("bad")
    with pytest.raises(RedisCacheOperationError):
        await cache.delete_async("bad")


def test_serialization_failure_expect_framework_cache_error() -> None:
    """직렬화 불가능한 값이 framework cache error로 변환되는지 검증한다."""
    cache: RedisCache[object] = RedisCache(
        config=RedisCacheConfig(),
        client=SyncRedisAdapter(
            RedisRawSyncClient(fakeredis.FakeRedis(server=fakeredis.FakeServer()))
        ),
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
