"""Backend-neutral application data cache contracts."""

from spakky.core.application.plugin import Plugin

from spakky.cache.backends.memory import InMemoryCache
from spakky.cache.error import AbstractSpakkyCacheError, InvalidCacheTTLError
from spakky.cache.interfaces.cache import AbstractCache, CacheTTL
from spakky.cache.result import CacheHit, CacheMiss, CacheResult

PLUGIN_NAME = Plugin(name="spakky-cache")
"""Plugin identifier for the Spakky Cache package."""

__all__ = [
    "AbstractCache",
    "AbstractSpakkyCacheError",
    "CacheHit",
    "CacheMiss",
    "CacheResult",
    "CacheTTL",
    "InMemoryCache",
    "InvalidCacheTTLError",
    "PLUGIN_NAME",
]
