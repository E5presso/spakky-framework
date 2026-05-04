"""Plugin initialization entry point."""

from spakky.core.application.application import SpakkyApplication

from spakky.cache.aspects.cache_aspect import AsyncCacheAspect, CacheAspect


def initialize(app: SpakkyApplication) -> None:
    """Initialize the spakky-cache plugin.

    Args:
        app: The SpakkyApplication instance.
    """
    app.add(CacheAspect)
    app.add(AsyncCacheAspect)
