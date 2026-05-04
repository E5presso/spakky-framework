"""Backend-neutral application data cache contracts."""

from spakky.core.application.plugin import Plugin

from spakky.cache.annotation import CacheEvict, Cacheable, cache_evict, cacheable
from spakky.cache.aspects.cache_aspect import AsyncCacheAspect, CacheAspect
from spakky.cache.error import (
    AbstractSpakkyCacheError,
    CacheBackendCapabilityError,
    CacheKeyGenerationError,
    InvalidCacheTTLError,
)
from spakky.cache.interfaces.cache import (
    ICache,
    ICacheMetrics,
    IStampedeProtectedCache,
    ITaggedCache,
    IWritePolicyCache,
    CacheTTL,
)
from spakky.cache.result import CacheHit, CacheMetricsSnapshot, CacheMiss, CacheResult

PLUGIN_NAME = Plugin(name="spakky-cache")
"""Plugin identifier for the Spakky Cache package."""

__all__ = [
    "ICache",
    "AbstractSpakkyCacheError",
    "AsyncCacheAspect",
    "CacheBackendCapabilityError",
    "CacheEvict",
    "CacheHit",
    "CacheKeyGenerationError",
    "CacheMetricsSnapshot",
    "CacheMiss",
    "CacheResult",
    "CacheTTL",
    "CacheAspect",
    "Cacheable",
    "ICacheMetrics",
    "IStampedeProtectedCache",
    "ITaggedCache",
    "IWritePolicyCache",
    "InvalidCacheTTLError",
    "PLUGIN_NAME",
    "cache_evict",
    "cacheable",
]
