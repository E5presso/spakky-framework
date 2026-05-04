"""Cache method annotations."""

from dataclasses import dataclass
from typing import Callable

from spakky.core.common.annotation import FunctionAnnotation

from spakky.cache.interfaces.cache import CacheTTL


@dataclass
class Cacheable(FunctionAnnotation):
    """Annotation for caching method return values."""

    key: str | None = None
    """Optional format string used as the cache key."""

    ttl: CacheTTL = None
    """Optional cache entry TTL."""

    tags: tuple[str, ...] = ()
    """Optional tags associated with the stored cache entry."""


@dataclass
class CacheEvict(FunctionAnnotation):
    """Annotation for evicting a cache entry after successful method execution."""

    key: str | None = None
    """Optional format string used as the cache key."""

    tags: tuple[str, ...] = ()
    """Optional cache tags to evict after successful method execution."""


def cacheable[**P, R](
    key: str | None = None,
    *,
    ttl: CacheTTL = None,
    tags: tuple[str, ...] = (),
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate a method so its return value is cached by AOP."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        return Cacheable(key=key, ttl=ttl, tags=tags)(func)

    return decorator


def cache_evict[**P, R](
    key: str | None = None,
    *,
    tags: tuple[str, ...] = (),
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate a method so its cache entry is evicted after success."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        return CacheEvict(key=key, tags=tags)(func)

    return decorator
