"""In-memory cache backend."""

from collections.abc import Callable
from datetime import timedelta
from time import monotonic
from typing import Generic, TypeVar

from typing_extensions import override

from spakky.cache.error import InvalidCacheTTLError
from spakky.cache.interfaces.cache import AbstractCache, CacheTTL
from spakky.cache.result import CacheHit, CacheMiss, CacheResult
from spakky.core.common.mutability import immutable
from spakky.core.pod.annotations.pod import Pod

T = TypeVar("T")


@immutable
class _CacheEntry(Generic[T]):
    value: T
    expires_at: float | None


@Pod()
class InMemoryCache(AbstractCache[T]):
    """Deterministic in-memory cache backend for one process."""

    def __init__(self, *, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._entries: dict[str, _CacheEntry[T]] = {}

    @override
    def get(self, key: str) -> CacheResult[T]:
        entry = self._entries.get(key)
        if entry is None:
            return CacheMiss()
        if self._is_expired(entry):
            self._entries.pop(key)
            return CacheMiss()
        return CacheHit(value=entry.value)

    @override
    def set(self, key: str, value: T, *, ttl: CacheTTL = None) -> None:
        expires_at = self._compute_expires_at(ttl)
        self._entries[key] = _CacheEntry(value=value, expires_at=expires_at)

    @override
    def delete(self, key: str) -> bool:
        return self._entries.pop(key, None) is not None

    @override
    def clear(self) -> None:
        self._entries.clear()

    @override
    async def get_async(self, key: str) -> CacheResult[T]:
        return self.get(key)

    @override
    async def set_async(self, key: str, value: T, *, ttl: CacheTTL = None) -> None:
        self.set(key, value, ttl=ttl)

    @override
    async def delete_async(self, key: str) -> bool:
        return self.delete(key)

    @override
    async def clear_async(self) -> None:
        self.clear()

    def _compute_expires_at(self, ttl: CacheTTL) -> float | None:
        if ttl is None:
            return None
        if isinstance(ttl, timedelta):
            ttl_seconds = ttl.total_seconds()
        else:
            ttl_seconds = float(ttl)
        if ttl_seconds <= 0:
            raise InvalidCacheTTLError()
        return self._clock() + ttl_seconds

    def _is_expired(self, entry: _CacheEntry[T]) -> bool:
        if entry.expires_at is None:
            return False
        return self._clock() >= entry.expires_at
