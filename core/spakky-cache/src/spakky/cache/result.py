"""Typed cache result contracts."""

from typing import Generic, TypeAlias, TypeVar

from spakky.core.common.mutability import immutable

T = TypeVar("T")


@immutable
class CacheHit(Generic[T]):
    """Cache lookup result for an existing entry."""

    value: T


@immutable
class CacheMiss:
    """Cache lookup result for a missing or expired entry."""


CacheResult: TypeAlias = CacheHit[T] | CacheMiss
"""Cache lookup result type."""
