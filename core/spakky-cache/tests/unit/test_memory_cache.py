"""Tests for the in-memory cache backend."""

from datetime import timedelta

import pytest

from spakky.cache import CacheHit, CacheMiss, InMemoryCache, InvalidCacheTTLError


class ManualClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_absent_key_get_expect_typed_miss_result() -> None:
    """missing key 조회가 typed miss result를 반환하는지 검증한다."""
    cache = InMemoryCache[str]()

    result = cache.get("missing")

    assert isinstance(result, CacheMiss)


def test_key_set_with_ttl_before_expiry_expect_hit_value() -> None:
    """TTL 만료 전 조회가 hit value를 반환하는지 검증한다."""
    clock = ManualClock()
    cache = InMemoryCache[str](clock=clock)

    cache.set("user:1", "Ada", ttl=timedelta(seconds=5))
    clock.advance(4)
    result = cache.get("user:1")

    assert isinstance(result, CacheHit)
    assert result.value == "Ada"


def test_key_set_with_float_ttl_after_expiry_expect_typed_miss() -> None:
    """TTL 만료 후 조회가 typed miss result를 반환하는지 검증한다."""
    clock = ManualClock()
    cache = InMemoryCache[str](clock=clock)

    cache.set("user:1", "Ada", ttl=1.5)
    clock.advance(1.5)
    result = cache.get("user:1")

    assert isinstance(result, CacheMiss)
    assert cache.delete("user:1") is False


def test_delete_and_clear_operations_expect_entries_removed_deterministically() -> None:
    """delete와 clear가 entry를 deterministic하게 제거하는지 검증한다."""
    cache = InMemoryCache[int]()

    cache.set("a", 1)
    cache.set("b", 2)

    assert cache.delete("a") is True
    assert isinstance(cache.get("a"), CacheMiss)
    assert isinstance(cache.get("b"), CacheHit)

    cache.clear()

    assert isinstance(cache.get("b"), CacheMiss)


def test_invalid_ttl_expect_cache_error() -> None:
    """0 이하 TTL이 cache error를 발생시키는지 검증한다."""
    cache = InMemoryCache[str]()

    with pytest.raises(InvalidCacheTTLError):
        cache.set("invalid", "value", ttl=0)


async def test_async_contract_behavior_expect_matches_sync_semantics() -> None:
    """async contract가 sync와 같은 hit/miss/delete/clear 의미를 갖는지 검증한다."""
    clock = ManualClock()
    cache = InMemoryCache[str](clock=clock)

    await cache.set_async("session", "active", ttl=2)
    hit = await cache.get_async("session")

    assert isinstance(hit, CacheHit)
    assert hit.value == "active"

    clock.advance(2)
    expired = await cache.get_async("session")

    assert isinstance(expired, CacheMiss)

    await cache.set_async("session", "active")
    assert await cache.delete_async("session") is True

    await cache.set_async("session", "active")
    await cache.clear_async()

    assert isinstance(await cache.get_async("session"), CacheMiss)
