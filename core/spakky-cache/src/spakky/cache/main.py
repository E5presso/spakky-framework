"""Plugin initialization entry point."""

from spakky.core.application.application import SpakkyApplication

from spakky.cache.aspects.cache_aspect import AsyncCacheAspect, CacheAspect
from spakky.cache.backends.memory import InMemoryCache


def initialize(app: SpakkyApplication) -> None:
    """Initialize the spakky-cache plugin.

    Args:
        app: The SpakkyApplication instance.
    """
    app.add(InMemoryCache)
    app.add(CacheAspect)
    app.add(AsyncCacheAspect)
