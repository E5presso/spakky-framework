"""Tests for cache annotations and AOP aspects."""

from datetime import timedelta

import pytest

from spakky.cache import (
    ICache,
    IStampedeProtectedCache,
    ITaggedCache,
    AbstractSpakkyCacheError,
    CacheBackendCapabilityError,
    CacheHit,
    CacheKeyGenerationError,
    CacheMiss,
    CacheResult,
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


class FailingCache(ICache[object]):
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


class RecordingCache(ICache[object]):
    def __init__(self) -> None:
        self._entries: dict[str, object] = {}

    def get(self, key: str) -> CacheResult[object]:
        if key not in self._entries:
            return CacheMiss()
        return CacheHit(value=self._entries[key])

    def set(self, key: str, value: object, *, ttl: CacheTTL = None) -> None:
        self._entries[key] = value

    def delete(self, key: str) -> bool:
        return self._entries.pop(key, None) is not None

    def clear(self) -> None:
        self._entries.clear()

    async def get_async(self, key: str) -> CacheResult[object]:
        return self.get(key)

    async def set_async(self, key: str, value: object, *, ttl: CacheTTL = None) -> None:
        self.set(key, value, ttl=ttl)

    async def delete_async(self, key: str) -> bool:
        return self.delete(key)

    async def clear_async(self) -> None:
        self.clear()


class TaggedRecordingCache(RecordingCache, ITaggedCache[object]):
    def __init__(self) -> None:
        super().__init__()
        self._tag_index: dict[str, set[str]] = {}

    def set_with_tags(
        self,
        key: str,
        value: object,
        *,
        tags: tuple[str, ...],
        ttl: CacheTTL = None,
    ) -> None:
        self.set(key, value, ttl=ttl)
        for tag in tags:
            self._tag_index.setdefault(tag, set()).add(key)

    def evict_tags(self, *tags: str) -> int:
        keys = {key for tag in tags for key in self._tag_index.get(tag, set())}
        for key in keys:
            self.delete(key)
        for tag in tags:
            self._tag_index.pop(tag, None)
        return len(keys)

    async def set_with_tags_async(
        self,
        key: str,
        value: object,
        *,
        tags: tuple[str, ...],
        ttl: CacheTTL = None,
    ) -> None:
        self.set_with_tags(key, value, tags=tags, ttl=ttl)

    async def evict_tags_async(self, *tags: str) -> int:
        return self.evict_tags(*tags)


class StampedeRecordingCache(RecordingCache, IStampedeProtectedCache[object]):
    def get_or_set(
        self,
        key: str,
        factory,
        *,
        ttl: CacheTTL = None,
        tags: tuple[str, ...] = (),
    ) -> object:
        cached = self.get(key)
        if isinstance(cached, CacheHit):
            return cached.value
        value = factory()
        self.set(key, value, ttl=ttl)
        return value

    async def get_or_set_async(
        self,
        key: str,
        factory,
        *,
        ttl: CacheTTL = None,
        tags: tuple[str, ...] = (),
    ) -> object:
        cached = await self.get_async(key)
        if isinstance(cached, CacheHit):
            return cached.value
        value = await factory()
        await self.set_async(key, value, ttl=ttl)
        return value


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

    @cacheable(key="tagged:{0}", tags=("profile",))
    def compute_tagged(self, value: int) -> str:
        self.calls += 1
        return f"tagged:{value}:{self.calls}"

    @cache_evict(tags=("profile",))
    def evict_profile_tag(self) -> str:
        self.calls += 1
        return f"tag-evict:{self.calls}"

    @cache_evict(tags=("profile",))
    async def evict_profile_tag_async(self) -> str:
        self.calls += 1
        return f"async-tag-evict:{self.calls}"

    @cacheable()
    async def compute_async(self, value: int) -> str:
        self.calls += 1
        return f"async:{value}:{self.calls}"

    @cacheable(key="async-tagged:{0}", tags=("profile",))
    async def compute_tagged_async(self, value: int) -> str:
        self.calls += 1
        return f"async-tagged:{value}:{self.calls}"

    @cache_evict(key="manual:{0}")
    async def evict_manual_key_async(self, value: int) -> str:
        self.calls += 1
        return f"async-evict:{value}:{self.calls}"


def test_cacheable_sync_method_expect_second_call_uses_cached_value() -> None:
    """cacheable sync method가 같은 입력에서 method 실행을 1회로 줄이는지 검증한다."""
    cache = RecordingCache()
    aspect = CacheAspect(cache)
    service = CounterService()

    first = aspect.around(service.compute, 7)
    second = aspect.around(service.compute, 7)

    assert first == second == "sync:7:1"
    assert service.calls == 1
    assert Aspect.get(aspect).matches(service.compute) is True


def test_cacheable_default_key_expect_keyword_order_is_deterministic() -> None:
    """default key generation이 kwargs 순서와 무관하게 deterministic한지 검증한다."""
    cache = RecordingCache()
    aspect = CacheAspect(cache)
    service = CounterService()

    first = aspect.around(service.compute_with_kwargs, prefix="user", value=7)
    second = aspect.around(service.compute_with_kwargs, value=7, prefix="user")

    assert first == second == "user:7:1"
    assert service.calls == 1


async def test_cacheable_async_method_expect_second_call_uses_cached_value() -> None:
    """cacheable async method가 같은 입력에서 async method 실행을 1회로 줄이는지 검증한다."""
    cache = RecordingCache()
    aspect = AsyncCacheAspect(cache)
    service = CounterService()

    first = await aspect.around_async(service.compute_async, 9)
    second = await aspect.around_async(service.compute_async, 9)

    assert first == second == "async:9:1"
    assert service.calls == 1
    assert AsyncAspect.get(aspect).matches(service.compute_async) is True


async def test_cacheable_async_tags_without_backend_capability_expect_cache_error() -> (
    None
):
    """async tagged cache annotation이 tag 미지원 backend에서 명시적으로 실패한다."""
    aspect = AsyncCacheAspect(RecordingCache())
    service = CounterService()

    with pytest.raises(CacheBackendCapabilityError):
        await aspect.around_async(service.compute_tagged_async, 11)


def test_cache_evict_method_expect_matching_entry_removed_after_success() -> None:
    """eviction annotation이 성공 후 matching cache entry를 제거하는지 검증한다."""
    cache = RecordingCache()
    aspect = CacheAspect(cache)
    service = CounterService()

    cached = aspect.around(service.compute_with_manual_key, 3)
    assert cached == "manual:3:1"
    assert isinstance(cache.get("manual:3"), CacheHit)

    evicted = aspect.around(service.evict_manual_key, 3)

    assert evicted == "evict:3:2"
    assert isinstance(cache.get("manual:3"), CacheMiss)


def test_cacheable_tags_expect_backend_tag_index_used() -> None:
    """tagged cacheable method가 backend tag index에 저장되는지 검증한다."""
    cache = TaggedRecordingCache()
    aspect = CacheAspect(cache)
    service = CounterService()

    first = aspect.around(service.compute_tagged, 11)
    second = aspect.around(service.compute_tagged, 11)
    evicted = aspect.around(service.evict_profile_tag)

    assert first == second == "tagged:11:1"
    assert evicted == "tag-evict:2"
    assert isinstance(cache.get("tagged:11"), CacheMiss)


def test_cacheable_tags_without_backend_capability_expect_cache_error() -> None:
    """tagged cache annotation이 tag 미지원 backend에서 명시적으로 실패하는지 검증한다."""
    aspect = CacheAspect(RecordingCache())
    service = CounterService()

    with pytest.raises(CacheBackendCapabilityError):
        aspect.around(service.compute_tagged, 11)


def test_cache_evict_tags_without_backend_capability_expect_cache_error() -> None:
    """tag eviction annotation이 tag 미지원 backend에서 명시적으로 실패하는지 검증한다."""
    aspect = CacheAspect(RecordingCache())
    service = CounterService()

    with pytest.raises(CacheBackendCapabilityError):
        aspect.around(service.evict_profile_tag)


def test_stampede_backend_expect_get_or_set_path_used() -> None:
    """stampede 지원 backend는 cacheable 처리에서 get_or_set 경로를 사용하는지 검증한다."""
    cache = StampedeRecordingCache()
    aspect = CacheAspect(cache)
    service = CounterService()

    first = aspect.around(service.compute, 12)
    second = aspect.around(service.compute, 12)

    assert first == second == "sync:12:1"
    assert service.calls == 1


def test_cache_evict_method_failure_expect_matching_entry_preserved() -> None:
    """eviction annotation이 method 실패 시 matching cache entry를 보존하는지 검증한다."""
    cache = RecordingCache()
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
    cache = RecordingCache()
    sync_aspect = CacheAspect(cache)
    async_aspect = AsyncCacheAspect(cache)
    service = CounterService()

    cached = sync_aspect.around(service.compute_with_manual_key, 5)
    assert cached == "manual:5:1"
    assert isinstance(cache.get("manual:5"), CacheHit)

    evicted = await async_aspect.around_async(service.evict_manual_key_async, 5)

    assert evicted == "async-evict:5:2"
    assert isinstance(cache.get("manual:5"), CacheMiss)


async def test_cacheable_async_tags_expect_backend_tag_index_used() -> None:
    """async tagged cacheable method가 backend tag index에 저장되는지 검증한다."""
    cache = TaggedRecordingCache()
    aspect = AsyncCacheAspect(cache)
    service = CounterService()

    first = await aspect.around_async(service.compute_tagged_async, 13)
    second = await aspect.around_async(service.compute_tagged_async, 13)
    evicted = await aspect.around_async(service.evict_profile_tag_async)

    assert first == second == "async-tagged:13:1"
    assert evicted == "async-tag-evict:2"
    assert isinstance(cache.get("async-tagged:13"), CacheMiss)


async def test_cache_evict_async_tags_without_backend_capability_expect_cache_error() -> (
    None
):
    """async tag eviction annotation이 tag 미지원 backend에서 명시적으로 실패한다."""
    aspect = AsyncCacheAspect(RecordingCache())
    service = CounterService()

    with pytest.raises(CacheBackendCapabilityError):
        await aspect.around_async(service.evict_profile_tag_async)


async def test_async_stampede_backend_expect_get_or_set_path_used() -> None:
    """async stampede 지원 backend는 get_or_set_async 경로를 사용하는지 검증한다."""
    cache = StampedeRecordingCache()
    aspect = AsyncCacheAspect(cache)
    service = CounterService()

    first = await aspect.around_async(service.compute_async, 14)
    second = await aspect.around_async(service.compute_async, 14)

    assert first == second == "async:14:1"
    assert service.calls == 1


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
    aspect = CacheAspect(RecordingCache())
    service = CounterService()

    with pytest.raises(CacheKeyGenerationError):
        aspect.around(service.bad_key)
