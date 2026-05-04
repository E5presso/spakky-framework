"""Backend-neutral cache contract."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from datetime import timedelta

from spakky.cache.result import CacheMetricsSnapshot, CacheResult

type CacheTTL = float | int | timedelta | None
"""Cache entry lifetime. None means no automatic expiry."""


class ICache[T](ABC):
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


class ITaggedCache[T](ICache[T], ABC):
    """Cache backend that can index and evict entries by tag."""

    @abstractmethod
    def set_with_tags(
        self,
        key: str,
        value: T,
        *,
        tags: tuple[str, ...],
        ttl: CacheTTL = None,
    ) -> None:
        """Store a value and associate it with cache tags."""
        ...

    @abstractmethod
    def evict_tags(self, *tags: str) -> int:
        """Remove entries associated with one or more tags."""
        ...

    @abstractmethod
    async def set_with_tags_async(
        self,
        key: str,
        value: T,
        *,
        tags: tuple[str, ...],
        ttl: CacheTTL = None,
    ) -> None:
        """Async variant of set_with_tags."""
        ...

    @abstractmethod
    async def evict_tags_async(self, *tags: str) -> int:
        """Async variant of evict_tags."""
        ...


class IStampedeProtectedCache[T](ICache[T], ABC):
    """Cache backend that serializes concurrent miss population."""

    @abstractmethod
    def get_or_set(
        self,
        key: str,
        factory: Callable[[], T],
        *,
        ttl: CacheTTL = None,
        tags: tuple[str, ...] = (),
    ) -> T:
        """Return cached value or populate it once through a backend lock."""
        ...

    @abstractmethod
    async def get_or_set_async(
        self,
        key: str,
        factory: Callable[[], Awaitable[T]],
        *,
        ttl: CacheTTL = None,
        tags: tuple[str, ...] = (),
    ) -> T:
        """Async variant of get_or_set."""
        ...


class ICacheMetrics[T](ICache[T], ABC):
    """Cache backend that exposes deterministic metrics counters."""

    @abstractmethod
    def metrics(self) -> CacheMetricsSnapshot:
        """Return a point-in-time metrics snapshot."""
        ...


class IWritePolicyCache[T](ICache[T], ABC):
    """Cache backend that coordinates cache writes with an origin writer."""

    @abstractmethod
    def write_through(
        self,
        key: str,
        value: T,
        writer: Callable[[T], None],
        *,
        ttl: CacheTTL = None,
        tags: tuple[str, ...] = (),
    ) -> None:
        """Write to the origin first, then update the cache."""
        ...

    @abstractmethod
    def write_behind(
        self,
        key: str,
        value: T,
        writer: Callable[[T], None],
        *,
        ttl: CacheTTL = None,
        tags: tuple[str, ...] = (),
    ) -> None:
        """Update the cache first, then invoke the origin writer."""
        ...

    @abstractmethod
    async def write_through_async(
        self,
        key: str,
        value: T,
        writer: Callable[[T], Awaitable[None]],
        *,
        ttl: CacheTTL = None,
        tags: tuple[str, ...] = (),
    ) -> None:
        """Async variant of write_through."""
        ...

    @abstractmethod
    async def write_behind_async(
        self,
        key: str,
        value: T,
        writer: Callable[[T], Awaitable[None]],
        *,
        ttl: CacheTTL = None,
        tags: tuple[str, ...] = (),
    ) -> None:
        """Async variant of write_behind."""
        ...
