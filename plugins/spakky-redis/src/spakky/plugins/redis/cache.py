"""Redis implementation of the spakky-cache contract."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
import pickle
from typing import Generic, TypeVar

from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError
from typing_extensions import override

from spakky.cache import ICache, CacheHit, CacheMiss, CacheResult, CacheTTL
from spakky.cache.error import InvalidCacheTTLError
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.redis.common.config import RedisCacheConfig
from spakky.plugins.redis.error import (
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
    def delete(self, *names: RedisKey) -> int: ...

    @abstractmethod
    def scan_iter(self, match: str) -> Iterator[RedisKey]: ...


class IAsyncRedisClient(ABC):
    """Explicit async Redis boundary used by RedisCache."""

    @abstractmethod
    async def get(self, name: str) -> bytes | None: ...

    @abstractmethod
    async def set(self, name: str, value: bytes, *, px: int | None = None) -> None: ...

    @abstractmethod
    async def delete(self, *names: RedisKey) -> int: ...

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
    def delete(self, *names: RedisKey) -> object: ...

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
    async def delete(self, *names: RedisKey) -> object: ...

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
    def delete(self, *names: RedisKey) -> object:
        return self._raw.delete(*names)

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
    async def delete(self, *names: RedisKey) -> object:
        return await self._raw.delete(*names)

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
    def delete(self, *names: RedisKey) -> int:
        try:
            deleted = self._raw.delete(*names)
        except RedisError as e:
            raise RedisCacheOperationError from e
        if isinstance(deleted, int):
            return deleted
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
    async def delete(self, *names: RedisKey) -> int:
        try:
            deleted = await self._raw.delete(*names)
        except RedisError as e:
            raise RedisCacheOperationError from e
        if isinstance(deleted, int):
            return deleted
        raise RedisCacheOperationError

    @override
    def scan_iter(self, match: str) -> AsyncIterator[RedisKey]:
        try:
            return self._raw.scan_iter(match=match)
        except RedisError as e:
            raise RedisCacheOperationError from e


@Pod()
class RedisCache(ICache[T], Generic[T]):
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
