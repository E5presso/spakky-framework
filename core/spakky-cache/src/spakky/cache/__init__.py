"""Backend-neutral application data cache contracts."""

from spakky.core.application.plugin import Plugin

from spakky.cache.annotation import CacheEvict, Cacheable, cache_evict, cacheable
from spakky.cache.aspects.cache_aspect import AsyncCacheAspect, CacheAspect
from spakky.cache.backends.memory import InMemoryCache
from spakky.cache.error import (
    AbstractSpakkyCacheError,
    CacheKeyGenerationError,
    InvalidCacheTTLError,
)
from spakky.cache.interfaces.cache import ICache, CacheTTL
from spakky.cache.result import CacheHit, CacheMiss, CacheResult

PLUGIN_NAME = Plugin(name="spakky-cache")
"""Plugin identifier for the Spakky Cache package."""

__all__ = [
    "ICache",
    "AbstractSpakkyCacheError",
    "AsyncCacheAspect",
    "CacheEvict",
    "CacheHit",
    "CacheKeyGenerationError",
    "CacheMiss",
    "CacheResult",
    "CacheTTL",
    "CacheAspect",
    "Cacheable",
    "InMemoryCache",
    "InvalidCacheTTLError",
    "PLUGIN_NAME",
    "cache_evict",
    "cacheable",
]
