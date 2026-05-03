"""Cache method annotations."""

from dataclasses import dataclass
from typing import Callable, ParamSpec, TypeVar

from spakky.core.common.annotation import FunctionAnnotation

from spakky.cache.interfaces.cache import CacheTTL

P = ParamSpec("P")
R = TypeVar("R")


@dataclass
class Cacheable(FunctionAnnotation):
    """Annotation for caching method return values."""

    key: str | None = None
    """Optional format string used as the cache key."""

    ttl: CacheTTL = None
    """Optional cache entry TTL."""


@dataclass
class CacheEvict(FunctionAnnotation):
    """Annotation for evicting a cache entry after successful method execution."""

    key: str | None = None
    """Optional format string used as the cache key."""


def cacheable(
    key: str | None = None,
    *,
    ttl: CacheTTL = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate a method so its return value is cached by AOP."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        return Cacheable(key=key, ttl=ttl)(func)

    return decorator


def cache_evict(
    key: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate a method so its cache entry is evicted after success."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        return CacheEvict(key=key)(func)

    return decorator
