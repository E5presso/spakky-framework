"""Redis implementation of the spakky-cache contract."""

from collections.abc import AsyncIterator, Awaitable, Iterator
from datetime import timedelta
import pickle
from typing import Generic, Protocol, TypeVar

from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError
from typing_extensions import override

from spakky.cache import AbstractCache, CacheHit, CacheMiss, CacheResult, CacheTTL
from spakky.cache.error import InvalidCacheTTLError
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.redis.common.config import RedisCacheConfig
from spakky.plugins.redis.error import (
    RedisCacheOperationError,
    RedisCacheSerializationError,
)

T = TypeVar("T")
RedisKey = str | bytes


class SyncRedisClient(Protocol):
    """Sync Redis operations used by RedisCache."""

    def ping(self) -> object: ...

    def get(self, name: str) -> bytes | None: ...

    def set(self, name: str, value: bytes, *, px: int | None = None) -> object: ...

    def delete(self, *names: RedisKey) -> int: ...

    def scan_iter(self, match: str) -> Iterator[RedisKey]: ...


class AsyncRedisClient(Protocol):
    """Async Redis operations used by RedisCache."""

    async def get(self, name: str) -> bytes | None: ...

    async def set(
        self, name: str, value: bytes, *, px: int | None = None
    ) -> object: ...

    async def delete(self, *names: RedisKey) -> int: ...

    def scan_iter(self, match: str) -> AsyncIterator[RedisKey]: ...


class RawSyncRedisClient(Protocol):
    """Redis-compatible sync client before response narrowing."""

    def ping(self) -> object: ...

    def get(self, name: str) -> object: ...

    def set(self, name: str, value: bytes, *, px: int | None = None) -> object: ...

    def delete(self, *names: RedisKey) -> object: ...

    def scan_iter(self, match: str) -> Iterator[RedisKey]: ...


class RawAsyncRedisClient(Protocol):
    """Redis-compatible async client before response narrowing."""

    def get(self, name: str) -> object: ...

    def set(self, name: str, value: bytes, *, px: int | None = None) -> object: ...

    def delete(self, *names: RedisKey) -> object: ...

    def scan_iter(self, match: str) -> AsyncIterator[RedisKey]: ...


class SyncRedisAdapter:
    """Typed boundary over the redis-py sync client."""

    def __init__(self, raw: RawSyncRedisClient) -> None:
        self._raw = raw

    def ping(self) -> object:
        try:
            return self._raw.ping()
        except RedisError as e:
            raise RedisCacheOperationError from e

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

    def set(self, name: str, value: bytes, *, px: int | None = None) -> object:
        try:
            return self._raw.set(name, value, px=px)
        except RedisError as e:
            raise RedisCacheOperationError from e

    def delete(self, *names: RedisKey) -> int:
        try:
            deleted = self._raw.delete(*names)
        except RedisError as e:
            raise RedisCacheOperationError from e
        if isinstance(deleted, int):
            return deleted
        raise RedisCacheOperationError

    def scan_iter(self, match: str) -> Iterator[RedisKey]:
        try:
            return self._raw.scan_iter(match=match)
        except RedisError as e:
            raise RedisCacheOperationError from e


class AsyncRedisAdapter:
    """Typed boundary over the redis-py async client."""

    def __init__(self, raw: RawAsyncRedisClient) -> None:
        self._raw = raw

    async def get(self, name: str) -> bytes | None:
        try:
            payload = await self._resolve(self._raw.get(name))
        except RedisError as e:
            raise RedisCacheOperationError from e
        if payload is None:
            return None
        if isinstance(payload, bytes):
            return payload
        raise RedisCacheOperationError

    async def set(self, name: str, value: bytes, *, px: int | None = None) -> object:
        try:
            return await self._resolve(self._raw.set(name, value, px=px))
        except RedisError as e:
            raise RedisCacheOperationError from e

    async def delete(self, *names: RedisKey) -> int:
        try:
            deleted = await self._resolve(self._raw.delete(*names))
        except RedisError as e:
            raise RedisCacheOperationError from e
        if isinstance(deleted, int):
            return deleted
        raise RedisCacheOperationError

    def scan_iter(self, match: str) -> AsyncIterator[RedisKey]:
        return self._raw.scan_iter(match=match)

    async def _resolve(self, response: object) -> object:
        if isinstance(response, Awaitable):
            return await response
        return response


@Pod()
class RedisCache(AbstractCache[T], Generic[T]):
    """Redis-backed cache that stores pickled values under a configured prefix."""

    def __init__(
        self,
        config: RedisCacheConfig | None = None,
        *,
        client: RawSyncRedisClient | None = None,
        async_client: RawAsyncRedisClient | None = None,
    ) -> None:
        self._config = config or RedisCacheConfig()
        self._client = SyncRedisAdapter(client or self._create_client())
        self._async_client = AsyncRedisAdapter(
            async_client or self._create_async_client()
        )
        self._ping()

    @override
    def get(self, key: str) -> CacheResult[T]:
        payload = self._client.get(self._redis_key(key))
        if payload is None:
            return CacheMiss()
        return CacheHit(value=self._deserialize(payload))

    @override
    def set(self, key: str, value: T, *, ttl: CacheTTL = None) -> None:
        payload = self._serialize(value)
        ttl_ms = self._ttl_ms(ttl)
        self._client.set(self._redis_key(key), payload, px=ttl_ms)

    @override
    def delete(self, key: str) -> bool:
        return self._client.delete(self._redis_key(key)) > 0

    @override
    def clear(self) -> None:
        keys = list(self._client.scan_iter(match=f"{self._config.key_prefix}*"))
        if keys:
            self._client.delete(*keys)

    @override
    async def get_async(self, key: str) -> CacheResult[T]:
        payload = await self._async_client.get(self._redis_key(key))
        if payload is None:
            return CacheMiss()
        return CacheHit(value=self._deserialize(payload))

    @override
    async def set_async(self, key: str, value: T, *, ttl: CacheTTL = None) -> None:
        payload = self._serialize(value)
        ttl_ms = self._ttl_ms(ttl)
        await self._async_client.set(self._redis_key(key), payload, px=ttl_ms)

    @override
    async def delete_async(self, key: str) -> bool:
        return await self._async_client.delete(self._redis_key(key)) > 0

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

    def _create_client(self) -> RawSyncRedisClient:
        return Redis.from_url(
            self._config.connection_url,
            username=self._config.username,
            password=self._config.password,
            socket_timeout=self._config.socket_timeout,
        )

    def _create_async_client(self) -> RawAsyncRedisClient:
        return AsyncRedis.from_url(
            self._config.connection_url,
            username=self._config.username,
            password=self._config.password,
            socket_timeout=self._config.socket_timeout,
        )

    def _ping(self) -> None:
        self._client.ping()

    def _redis_key(self, key: str) -> str:
        return f"{self._config.key_prefix}{key}"

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
