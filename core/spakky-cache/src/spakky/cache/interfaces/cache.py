"""Backend-neutral cache contract."""

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Generic, TypeAlias, TypeVar

from spakky.cache.result import CacheResult

CacheTTL: TypeAlias = float | int | timedelta | None
"""Cache entry lifetime. None means no automatic expiry."""

T = TypeVar("T")


class ICache(ABC, Generic[T]):
    """Backend-neutral application data cache contract."""

    @abstractmethod
    def get(self, key: str) -> CacheResult[T]:
        """Return a typed hit or miss result for a cache key."""
        ...

    @abstractmethod
    def set(self, key: str, value: T, *, ttl: CacheTTL = None) -> None:
        """Store a cache value with an optional TTL."""
        ...

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Remove one cache key and return whether an entry existed."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Remove all cache entries from this backend instance."""
        ...

    @abstractmethod
    async def get_async(self, key: str) -> CacheResult[T]:
        """Async variant of get."""
        ...

    @abstractmethod
    async def set_async(self, key: str, value: T, *, ttl: CacheTTL = None) -> None:
        """Async variant of set."""
        ...

    @abstractmethod
    async def delete_async(self, key: str) -> bool:
        """Async variant of delete."""
        ...

    @abstractmethod
    async def clear_async(self) -> None:
        """Async variant of clear."""
        ...
