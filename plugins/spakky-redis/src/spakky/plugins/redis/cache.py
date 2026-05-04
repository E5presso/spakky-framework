"""Redis implementation of the spakky-cache contract."""

from abc import ABC, abstractmethod
from asyncio import sleep as async_sleep
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Set
from datetime import timedelta
import pickle
from time import monotonic, sleep
from typing import Generic, TypeVar
from uuid import uuid4

from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError
from typing_extensions import override

from spakky.cache import (
    ICacheMetrics,
    IStampedeProtectedCache,
    ITaggedCache,
    IWritePolicyCache,
    CacheHit,
    CacheMetricsSnapshot,
    CacheMiss,
    CacheResult,
    CacheTTL,
)
from spakky.cache.error import InvalidCacheTTLError
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.redis.common.config import RedisCacheConfig
from spakky.plugins.redis.error import (
    RedisCacheLockTimeoutError,
    RedisCacheOperationError,
    RedisCacheSerializationError,
)

T = TypeVar("T")
RedisKey = str | bytes


class ISyncRedisClient(ABC):
    """Explicit sync Redis boundary used by RedisCache."""

    @abstractmethod
    def ping(self) -> None: ...

    @abstractmethod
    def get(self, name: str) -> bytes | None: ...

    @abstractmethod
    def set(self, name: str, value: bytes, *, px: int | None = None) -> None: ...

    @abstractmethod
    def set_if_absent(self, name: str, value: bytes, *, px: int) -> bool: ...

    @abstractmethod
    def delete(self, *names: RedisKey) -> int: ...

    @abstractmethod
    def add_set_members(self, name: str, *values: RedisKey) -> int: ...

    @abstractmethod
    def set_members(self, name: str) -> Set[RedisKey]: ...

    @abstractmethod
    def scan_iter(self, match: str) -> Iterator[RedisKey]: ...


class IAsyncRedisClient(ABC):
    """Explicit async Redis boundary used by RedisCache."""

    @abstractmethod
    async def get(self, name: str) -> bytes | None: ...

    @abstractmethod
    async def set(self, name: str, value: bytes, *, px: int | None = None) -> None: ...

    @abstractmethod
    async def set_if_absent(self, name: str, value: bytes, *, px: int) -> bool: ...

    @abstractmethod
    async def delete(self, *names: RedisKey) -> int: ...

    @abstractmethod
    async def add_set_members(self, name: str, *values: RedisKey) -> int: ...

    @abstractmethod
    async def set_members(self, name: str) -> Set[RedisKey]: ...

    @abstractmethod
    def scan_iter(self, match: str) -> AsyncIterator[RedisKey]: ...


class IRawSyncRedisClient(ABC):
    """Explicit raw sync Redis boundary before response narrowing."""

    @abstractmethod
    def ping(self) -> object: ...

    @abstractmethod
    def get(self, name: str) -> object: ...

    @abstractmethod
    def set(self, name: str, value: bytes, *, px: int | None = None) -> object: ...

    @abstractmethod
    def set_if_absent(self, name: str, value: bytes, *, px: int) -> object: ...

    @abstractmethod
    def delete(self, *names: RedisKey) -> object: ...

    @abstractmethod
    def add_set_members(self, name: str, *values: RedisKey) -> object: ...

    @abstractmethod
    def set_members(self, name: str) -> object: ...

    @abstractmethod
    def scan_iter(self, match: str) -> Iterator[RedisKey]: ...


class IRawAsyncRedisClient(ABC):
    """Explicit raw async Redis boundary before response narrowing."""

    @abstractmethod
    async def get(self, name: str) -> object: ...

    @abstractmethod
    async def set(
        self, name: str, value: bytes, *, px: int | None = None
    ) -> object: ...

    @abstractmethod
    async def set_if_absent(self, name: str, value: bytes, *, px: int) -> object: ...

    @abstractmethod
    async def delete(self, *names: RedisKey) -> object: ...

    @abstractmethod
    async def add_set_members(self, name: str, *values: RedisKey) -> object: ...

    @abstractmethod
    async def set_members(self, name: str) -> object: ...

    @abstractmethod
    def scan_iter(self, match: str) -> AsyncIterator[RedisKey]: ...


class RedisRawSyncClient(IRawSyncRedisClient):
    """Raw sync Redis client wrapper for redis-py."""

    def __init__(self, raw: Redis) -> None:
        self._raw = raw

    @override
    def ping(self) -> object:
        return self._raw.ping()

    @override
    def get(self, name: str) -> object:
        return self._raw.get(name)

    @override
    def set(self, name: str, value: bytes, *, px: int | None = None) -> object:
        return self._raw.set(name, value, px=px)

    @override
    def set_if_absent(self, name: str, value: bytes, *, px: int) -> object:
        return self._raw.set(name, value, px=px, nx=True)

    @override
    def delete(self, *names: RedisKey) -> object:
        return self._raw.delete(*names)

    @override
    def add_set_members(self, name: str, *values: RedisKey) -> object:
        return self._raw.sadd(name, *values)

    @override
    def set_members(self, name: str) -> object:
        return self._raw.smembers(name)

    @override
    def scan_iter(self, match: str) -> Iterator[RedisKey]:
        return self._raw.scan_iter(match=match)


class RedisRawAsyncClient(IRawAsyncRedisClient):
    """Raw async Redis client wrapper for redis-py."""

    def __init__(self, raw: AsyncRedis) -> None:
        self._raw = raw

    @override
    async def get(self, name: str) -> object:
        return await self._raw.get(name)

    @override
    async def set(self, name: str, value: bytes, *, px: int | None = None) -> object:
        return await self._raw.set(name, value, px=px)

    @override
    async def set_if_absent(self, name: str, value: bytes, *, px: int) -> object:
        return await self._raw.set(name, value, px=px, nx=True)

    @override
    async def delete(self, *names: RedisKey) -> object:
        return await self._raw.delete(*names)

    @override
    async def add_set_members(self, name: str, *values: RedisKey) -> object:
        return await self._raw.execute_command("SADD", name, *values)

    @override
    async def set_members(self, name: str) -> object:
        return await self._raw.execute_command("SMEMBERS", name)

    @override
    def scan_iter(self, match: str) -> AsyncIterator[RedisKey]:
        return self._raw.scan_iter(match=match)


class SyncRedisAdapter(ISyncRedisClient):
    """Typed boundary over the redis-py sync client."""

    def __init__(self, raw: IRawSyncRedisClient) -> None:
        self._raw = raw

    @override
    def ping(self) -> None:
        try:
            self._raw.ping()
        except RedisError as e:
            raise RedisCacheOperationError from e

    @override
    def get(self, name: str) -> bytes | None:
        try:
            payload = self._raw.get(name)
        except RedisError as e:
            raise RedisCacheOperationError from e
        if payload is None:
            return None
        if isinstance(payload, bytes):
            return payload
        raise RedisCacheOperationError

    @override
    def set(self, name: str, value: bytes, *, px: int | None = None) -> None:
        try:
            self._raw.set(name, value, px=px)
        except RedisError as e:
            raise RedisCacheOperationError from e

    @override
    def set_if_absent(self, name: str, value: bytes, *, px: int) -> bool:
        try:
            result = self._raw.set_if_absent(name, value, px=px)
        except RedisError as e:
            raise RedisCacheOperationError from e
        if result is None:
            return False
        if isinstance(result, bool):
            return result
        raise RedisCacheOperationError

    @override
    def delete(self, *names: RedisKey) -> int:
        try:
            deleted = self._raw.delete(*names)
        except RedisError as e:
            raise RedisCacheOperationError from e
        if isinstance(deleted, int):
            return deleted
        raise RedisCacheOperationError

    @override
    def add_set_members(self, name: str, *values: RedisKey) -> int:
        try:
            added = self._raw.add_set_members(name, *values)
        except RedisError as e:
            raise RedisCacheOperationError from e
        if isinstance(added, int):
            return added
        raise RedisCacheOperationError

    @override
    def set_members(self, name: str) -> Set[RedisKey]:
        try:
            members = self._raw.set_members(name)
        except RedisError as e:
            raise RedisCacheOperationError from e
        if isinstance(members, set):
            return members
        raise RedisCacheOperationError

    @override
    def scan_iter(self, match: str) -> Iterator[RedisKey]:
        try:
            return self._raw.scan_iter(match=match)
        except RedisError as e:
            raise RedisCacheOperationError from e


class AsyncRedisAdapter(IAsyncRedisClient):
    """Typed boundary over the redis-py async client."""

    def __init__(self, raw: IRawAsyncRedisClient) -> None:
        self._raw = raw

    @override
    async def get(self, name: str) -> bytes | None:
        try:
            payload = await self._raw.get(name)
        except RedisError as e:
            raise RedisCacheOperationError from e
        if payload is None:
            return None
        if isinstance(payload, bytes):
            return payload
        raise RedisCacheOperationError

    @override
    async def set(self, name: str, value: bytes, *, px: int | None = None) -> None:
        try:
            await self._raw.set(name, value, px=px)
        except RedisError as e:
            raise RedisCacheOperationError from e

    @override
    async def set_if_absent(self, name: str, value: bytes, *, px: int) -> bool:
        try:
            result = await self._raw.set_if_absent(name, value, px=px)
        except RedisError as e:
            raise RedisCacheOperationError from e
        if result is None:
            return False
        if isinstance(result, bool):
            return result
        raise RedisCacheOperationError

    @override
    async def delete(self, *names: RedisKey) -> int:
        try:
            deleted = await self._raw.delete(*names)
        except RedisError as e:
            raise RedisCacheOperationError from e
        if isinstance(deleted, int):
            return deleted
        raise RedisCacheOperationError

    @override
    async def add_set_members(self, name: str, *values: RedisKey) -> int:
        try:
            added = await self._raw.add_set_members(name, *values)
        except RedisError as e:
            raise RedisCacheOperationError from e
        if isinstance(added, int):
            return added
        raise RedisCacheOperationError

    @override
    async def set_members(self, name: str) -> Set[RedisKey]:
        try:
            members = await self._raw.set_members(name)
        except RedisError as e:
            raise RedisCacheOperationError from e
        if isinstance(members, set):
            return members
        raise RedisCacheOperationError

    @override
    def scan_iter(self, match: str) -> AsyncIterator[RedisKey]:
        try:
            return self._raw.scan_iter(match=match)
        except RedisError as e:
            raise RedisCacheOperationError from e


@Pod()
class RedisCache(
    ITaggedCache[T],
    IStampedeProtectedCache[T],
    ICacheMetrics[T],
    IWritePolicyCache[T],
    Generic[T],
):
    """Redis-backed cache that stores pickled values under a configured prefix."""

    def __init__(
        self,
        config: RedisCacheConfig | None = None,
        *,
        client: ISyncRedisClient | None = None,
        async_client: IAsyncRedisClient | None = None,
    ) -> None:
        self._config = config or RedisCacheConfig()
        self._client = client or self._create_client()
        self._async_client = async_client or self._create_async_client()
        self._hits = 0
        self._misses = 0
        self._writes = 0
        self._deletes = 0
        self._clears = 0
        self._tag_evictions = 0
        self._stampede_waits = 0
        self._ping()

    @override
    def get(self, key: str) -> CacheResult[T]:
        payload = self._client.get(self._redis_key(key))
        if payload is None:
            self._misses += 1
            return CacheMiss()
        self._hits += 1
        return CacheHit(value=self._deserialize(payload))

    @override
    def set(self, key: str, value: T, *, ttl: CacheTTL = None) -> None:
        payload = self._serialize(value)
        ttl_ms = self._ttl_ms(ttl)
        self._client.set(self._redis_key(key), payload, px=ttl_ms)
        self._writes += 1

    @override
    def delete(self, key: str) -> bool:
        deleted = self._client.delete(self._redis_key(key)) > 0
        if deleted:
            self._deletes += 1
        return deleted

    @override
    def clear(self) -> None:
        keys = list(self._client.scan_iter(match=f"{self._config.key_prefix}*"))
        if keys:
            self._client.delete(*keys)
        self._clears += 1

    @override
    def set_with_tags(
        self,
        key: str,
        value: T,
        *,
        tags: tuple[str, ...],
        ttl: CacheTTL = None,
    ) -> None:
        self.set(key, value, ttl=ttl)
        redis_key = self._redis_key(key)
        for tag in tags:
            self._client.add_set_members(self._tag_key(tag), redis_key)

    @override
    def evict_tags(self, *tags: str) -> int:
        keys = self._tagged_keys(tags)
        tag_keys = tuple(self._tag_key(tag) for tag in tags)
        names = keys + tag_keys
        if not names:
            return 0
        deleted = self._client.delete(*names)
        self._tag_evictions += 1
        return deleted

    @override
    async def get_async(self, key: str) -> CacheResult[T]:
        payload = await self._async_client.get(self._redis_key(key))
        if payload is None:
            self._misses += 1
            return CacheMiss()
        self._hits += 1
        return CacheHit(value=self._deserialize(payload))

    @override
    async def set_async(self, key: str, value: T, *, ttl: CacheTTL = None) -> None:
        payload = self._serialize(value)
        ttl_ms = self._ttl_ms(ttl)
        await self._async_client.set(self._redis_key(key), payload, px=ttl_ms)
        self._writes += 1

    @override
    async def delete_async(self, key: str) -> bool:
        deleted = await self._async_client.delete(self._redis_key(key)) > 0
        if deleted:
            self._deletes += 1
        return deleted

    @override
    async def clear_async(self) -> None:
        keys = [
            key
            async for key in self._async_client.scan_iter(
                match=f"{self._config.key_prefix}*"
            )
        ]
        if keys:
            await self._async_client.delete(*keys)
        self._clears += 1

    @override
    async def set_with_tags_async(
        self,
        key: str,
        value: T,
        *,
        tags: tuple[str, ...],
        ttl: CacheTTL = None,
    ) -> None:
        await self.set_async(key, value, ttl=ttl)
        redis_key = self._redis_key(key)
        for tag in tags:
            await self._async_client.add_set_members(self._tag_key(tag), redis_key)

    @override
    async def evict_tags_async(self, *tags: str) -> int:
        keys = await self._tagged_keys_async(tags)
        tag_keys = tuple(self._tag_key(tag) for tag in tags)
        names = keys + tag_keys
        if not names:
            return 0
        deleted = await self._async_client.delete(*names)
        self._tag_evictions += 1
        return deleted

    @override
    def get_or_set(
        self,
        key: str,
        factory: Callable[[], T],
        *,
        ttl: CacheTTL = None,
        tags: tuple[str, ...] = (),
    ) -> T:
        cached = self.get(key)
        if isinstance(cached, CacheHit):
            return cached.value

        lock_key = self._lock_key(key)
        token = uuid4().hex.encode()
        if self._client.set_if_absent(lock_key, token, px=self._lock_ttl_ms()):
            try:
                second_check = self.get(key)
                if isinstance(second_check, CacheHit):
                    return second_check.value
                value = factory()
                self.set_with_tags(key, value, tags=tags, ttl=ttl)
                return value
            finally:
                self._client.delete(lock_key)

        self._stampede_waits += 1
        return self._wait_for_value(key)

    @override
    async def get_or_set_async(
        self,
        key: str,
        factory: Callable[[], Awaitable[T]],
        *,
        ttl: CacheTTL = None,
        tags: tuple[str, ...] = (),
    ) -> T:
        cached = await self.get_async(key)
        if isinstance(cached, CacheHit):
            return cached.value

        lock_key = self._lock_key(key)
        token = uuid4().hex.encode()
        if await self._async_client.set_if_absent(
            lock_key,
            token,
            px=self._lock_ttl_ms(),
        ):
            try:
                second_check = await self.get_async(key)
                if isinstance(second_check, CacheHit):
                    return second_check.value
                value = await factory()
                await self.set_with_tags_async(key, value, tags=tags, ttl=ttl)
                return value
            finally:
                await self._async_client.delete(lock_key)

        self._stampede_waits += 1
        return await self._wait_for_value_async(key)

    @override
    def metrics(self) -> CacheMetricsSnapshot:
        return CacheMetricsSnapshot(
            hits=self._hits,
            misses=self._misses,
            writes=self._writes,
            deletes=self._deletes,
            clears=self._clears,
            tag_evictions=self._tag_evictions,
            stampede_waits=self._stampede_waits,
        )

    @override
    def write_through(
        self,
        key: str,
        value: T,
        writer: Callable[[T], None],
        *,
        ttl: CacheTTL = None,
        tags: tuple[str, ...] = (),
    ) -> None:
        writer(value)
        self.set_with_tags(key, value, tags=tags, ttl=ttl)

    @override
    def write_behind(
        self,
        key: str,
        value: T,
        writer: Callable[[T], None],
        *,
        ttl: CacheTTL = None,
        tags: tuple[str, ...] = (),
    ) -> None:
        self.set_with_tags(key, value, tags=tags, ttl=ttl)
        writer(value)

    @override
    async def write_through_async(
        self,
        key: str,
        value: T,
        writer: Callable[[T], Awaitable[None]],
        *,
        ttl: CacheTTL = None,
        tags: tuple[str, ...] = (),
    ) -> None:
        await writer(value)
        await self.set_with_tags_async(key, value, tags=tags, ttl=ttl)

    @override
    async def write_behind_async(
        self,
        key: str,
        value: T,
        writer: Callable[[T], Awaitable[None]],
        *,
        ttl: CacheTTL = None,
        tags: tuple[str, ...] = (),
    ) -> None:
        await self.set_with_tags_async(key, value, tags=tags, ttl=ttl)
        await writer(value)

    def _create_client(self) -> ISyncRedisClient:
        return SyncRedisAdapter(
            RedisRawSyncClient(
                Redis.from_url(
                    self._config.connection_url,
                    username=self._config.username,
                    password=self._config.password,
                    socket_timeout=self._config.socket_timeout,
                )
            )
        )

    def _create_async_client(self) -> IAsyncRedisClient:
        return AsyncRedisAdapter(
            RedisRawAsyncClient(
                AsyncRedis.from_url(
                    self._config.connection_url,
                    username=self._config.username,
                    password=self._config.password,
                    socket_timeout=self._config.socket_timeout,
                )
            )
        )

    def _ping(self) -> None:
        self._client.ping()

    def ping(self) -> None:
        """Validate that the configured Redis backend is reachable."""
        self._ping()

    def _redis_key(self, key: str) -> str:
        return f"{self._config.key_prefix}{key}"

    def _tag_key(self, tag: str) -> str:
        return f"{self._config.key_prefix}__tag__:{tag}"

    def _lock_key(self, key: str) -> str:
        return f"{self._config.key_prefix}__lock__:{key}"

    def _tagged_keys(self, tags: tuple[str, ...]) -> tuple[RedisKey, ...]:
        keys: set[RedisKey] = set()
        for tag in tags:
            keys.update(self._client.set_members(self._tag_key(tag)))
        return tuple(sorted(keys, key=str))

    async def _tagged_keys_async(self, tags: tuple[str, ...]) -> tuple[RedisKey, ...]:
        keys: set[RedisKey] = set()
        for tag in tags:
            keys.update(await self._async_client.set_members(self._tag_key(tag)))
        return tuple(sorted(keys, key=str))

    def _ttl_ms(self, ttl: CacheTTL) -> int | None:
        if ttl is None:
            return None
        if isinstance(ttl, timedelta):
            ttl_seconds = ttl.total_seconds()
        else:
            ttl_seconds = float(ttl)
        if ttl_seconds <= 0:
            raise InvalidCacheTTLError()
        return max(1, int(ttl_seconds * 1000))

    def _lock_ttl_ms(self) -> int:
        return 30_000

    def _wait_for_value(self, key: str) -> T:
        deadline = monotonic() + 30.0
        while monotonic() < deadline:
            cached = self.get(key)
            if isinstance(cached, CacheHit):
                return cached.value
            sleep(0.01)
        raise RedisCacheLockTimeoutError()

    async def _wait_for_value_async(self, key: str) -> T:
        deadline = monotonic() + 30.0
        while monotonic() < deadline:
            cached = await self.get_async(key)
            if isinstance(cached, CacheHit):
                return cached.value
            await async_sleep(0.01)
        raise RedisCacheLockTimeoutError()

    def _serialize(self, value: T) -> bytes:
        try:
            return pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        except (pickle.PickleError, AttributeError, TypeError) as e:
            raise RedisCacheSerializationError from e

    def _deserialize(self, payload: bytes) -> T:
        try:
            value = pickle.loads(payload)
        except (
            pickle.PickleError,
            EOFError,
            AttributeError,
            ImportError,
            IndexError,
        ) as e:
            raise RedisCacheSerializationError from e
        return value
