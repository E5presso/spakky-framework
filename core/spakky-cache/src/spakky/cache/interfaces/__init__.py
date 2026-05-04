"""Cache interface contracts."""

from spakky.cache.interfaces.cache import (
    ICache,
    ICacheMetrics,
    IStampedeProtectedCache,
    ITaggedCache,
    IWritePolicyCache,
)

__all__ = [
    "ICache",
    "ICacheMetrics",
    "IStampedeProtectedCache",
    "ITaggedCache",
    "IWritePolicyCache",
]
