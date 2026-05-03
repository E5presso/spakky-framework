"""Tests for cache annotations and AOP aspects."""

from datetime import timedelta

import pytest

from spakky.cache import (
    AbstractCache,
    AbstractSpakkyCacheError,
    CacheHit,
    CacheKeyGenerationError,
    CacheMiss,
    CacheResult,
    InMemoryCache,
    cache_evict,
    cacheable,
)
from spakky.cache.aspects.cache_aspect import AsyncCacheAspect, CacheAspect
from spakky.cache.interfaces.cache import CacheTTL
from spakky.core.aop.aspect import Aspect, AsyncAspect


class CacheBackendUnavailableError(AbstractSpakkyCacheError):
    message = "Cache backend unavailable"


class ServiceExecutionError(Exception):
    """Raised by the test service before eviction."""


class FailingCache(AbstractCache[object]):
    def get(self, key: str) -> CacheResult[object]:
        raise CacheBackendUnavailableError()

    def set(self, key: str, value: object, *, ttl: CacheTTL = None) -> None:
        raise CacheBackendUnavailableError()

    def delete(self, key: str) -> bool:
        raise CacheBackendUnavailableError()

    def clear(self) -> None:
        raise CacheBackendUnavailableError()

    async def get_async(self, key: str) -> CacheResult[object]:
        raise CacheBackendUnavailableError()

    async def set_async(self, key: str, value: object, *, ttl: CacheTTL = None) -> None:
        raise CacheBackendUnavailableError()

    async def delete_async(self, key: str) -> bool:
        raise CacheBackendUnavailableError()

    async def clear_async(self) -> None:
        raise CacheBackendUnavailableError()


class CounterService:
    def __init__(self) -> None:
        self.calls = 0

    @cacheable()
    def compute(self, value: int) -> str:
        self.calls += 1
        return f"sync:{value}:{self.calls}"

    @cacheable()
    def compute_with_kwargs(self, *, prefix: str, value: int) -> str:
        self.calls += 1
        return f"{prefix}:{value}:{self.calls}"

    @cacheable(key="manual:{0}", ttl=timedelta(seconds=5))
    def compute_with_manual_key(self, value: int) -> str:
        self.calls += 1
        return f"manual:{value}:{self.calls}"

    @cache_evict(key="manual:{0}")
    def evict_manual_key(self, value: int) -> str:
        self.calls += 1
        return f"evict:{value}:{self.calls}"

    @cache_evict(key="manual:{0}")
    def fail_before_evicting_manual_key(self, value: int) -> str:
        self.calls += 1
        raise ServiceExecutionError

    @cacheable(key="{missing}")
    def bad_key(self) -> str:
        self.calls += 1
        return "bad"

    @cacheable()
    async def compute_async(self, value: int) -> str:
        self.calls += 1
        return f"async:{value}:{self.calls}"

    @cache_evict(key="manual:{0}")
    async def evict_manual_key_async(self, value: int) -> str:
        self.calls += 1
        return f"async-evict:{value}:{self.calls}"


def test_cacheable_sync_method_expect_second_call_uses_cached_value() -> None:
    """cacheable sync method가 같은 입력에서 method 실행을 1회로 줄이는지 검증한다."""
    cache = InMemoryCache[object]()
    aspect = CacheAspect(cache)
    service = CounterService()

    first = aspect.around(service.compute, 7)
    second = aspect.around(service.compute, 7)

    assert first == second == "sync:7:1"
    assert service.calls == 1
    assert Aspect.get(aspect).matches(service.compute) is True


def test_cacheable_default_key_expect_keyword_order_is_deterministic() -> None:
    """default key generation이 kwargs 순서와 무관하게 deterministic한지 검증한다."""
    cache = InMemoryCache[object]()
    aspect = CacheAspect(cache)
    service = CounterService()

    first = aspect.around(service.compute_with_kwargs, prefix="user", value=7)
    second = aspect.around(service.compute_with_kwargs, value=7, prefix="user")

    assert first == second == "user:7:1"
    assert service.calls == 1


async def test_cacheable_async_method_expect_second_call_uses_cached_value() -> None:
    """cacheable async method가 같은 입력에서 async method 실행을 1회로 줄이는지 검증한다."""
    cache = InMemoryCache[object]()
    aspect = AsyncCacheAspect(cache)
    service = CounterService()

    first = await aspect.around_async(service.compute_async, 9)
    second = await aspect.around_async(service.compute_async, 9)

    assert first == second == "async:9:1"
    assert service.calls == 1
    assert AsyncAspect.get(aspect).matches(service.compute_async) is True


def test_cache_evict_method_expect_matching_entry_removed_after_success() -> None:
    """eviction annotation이 성공 후 matching cache entry를 제거하는지 검증한다."""
    cache = InMemoryCache[object]()
    aspect = CacheAspect(cache)
    service = CounterService()

    cached = aspect.around(service.compute_with_manual_key, 3)
    assert cached == "manual:3:1"
    assert isinstance(cache.get("manual:3"), CacheHit)

    evicted = aspect.around(service.evict_manual_key, 3)

    assert evicted == "evict:3:2"
    assert isinstance(cache.get("manual:3"), CacheMiss)


def test_cache_evict_method_failure_expect_matching_entry_preserved() -> None:
    """eviction annotation이 method 실패 시 matching cache entry를 보존하는지 검증한다."""
    cache = InMemoryCache[object]()
    aspect = CacheAspect(cache)
    service = CounterService()

    cached = aspect.around(service.compute_with_manual_key, 3)
    assert cached == "manual:3:1"

    with pytest.raises(ServiceExecutionError):
        aspect.around(service.fail_before_evicting_manual_key, 3)

    result = cache.get("manual:3")
    assert isinstance(result, CacheHit)
    assert result.value == "manual:3:1"


async def test_cache_evict_async_method_expect_matching_entry_removed_after_success() -> (
    None
):
    """async eviction annotation이 성공 후 matching cache entry를 제거하는지 검증한다."""
    cache = InMemoryCache[object]()
    sync_aspect = CacheAspect(cache)
    async_aspect = AsyncCacheAspect(cache)
    service = CounterService()

    cached = sync_aspect.around(service.compute_with_manual_key, 5)
    assert cached == "manual:5:1"
    assert isinstance(cache.get("manual:5"), CacheHit)

    evicted = await async_aspect.around_async(service.evict_manual_key_async, 5)

    assert evicted == "async-evict:5:2"
    assert isinstance(cache.get("manual:5"), CacheMiss)


def test_backend_failure_expect_cache_error_fails_loudly() -> None:
    """backend failure가 cache aspect에서 숨겨지지 않고 전파되는지 검증한다."""
    aspect = CacheAspect(FailingCache())
    service = CounterService()

    with pytest.raises(CacheBackendUnavailableError):
        aspect.around(service.compute, 1)


async def test_async_backend_failure_expect_cache_error_fails_loudly() -> None:
    """async backend failure가 cache aspect에서 숨겨지지 않고 전파되는지 검증한다."""
    aspect = AsyncCacheAspect(FailingCache())
    service = CounterService()

    with pytest.raises(CacheBackendUnavailableError):
        await aspect.around_async(service.compute_async, 1)


def test_bad_key_template_expect_cache_key_generation_error() -> None:
    """key template이 입력과 맞지 않으면 cache key error로 실패하는지 검증한다."""
    aspect = CacheAspect(InMemoryCache[object]())
    service = CounterService()

    with pytest.raises(CacheKeyGenerationError):
        aspect.around(service.bad_key)
