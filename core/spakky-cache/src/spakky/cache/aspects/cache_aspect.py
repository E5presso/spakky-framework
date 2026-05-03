"""AOP aspects for cache annotations."""

from inspect import iscoroutinefunction

from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.aop.pointcut import Around
from spakky.core.common.types import AsyncFunc, Func
from spakky.core.pod.annotations.order import Order

from spakky.cache.annotation import CacheEvict, Cacheable
from spakky.cache.error import CacheKeyGenerationError
from spakky.cache.interfaces.cache import ICache
from spakky.cache.result import CacheHit


def _matches_sync(method: Func) -> bool:
    return (
        Cacheable.exists(method) or CacheEvict.exists(method)
    ) and not iscoroutinefunction(method)


def _matches_async(method: Func) -> bool:
    return (
        Cacheable.exists(method) or CacheEvict.exists(method)
    ) and iscoroutinefunction(method)


def _key_from_call(
    joinpoint: Func,
    configured_key: str | None,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> str:
    try:
        if configured_key is not None:
            return configured_key.format(*args, **kwargs)
        ordered_kwargs = tuple(sorted(kwargs.items(), key=lambda item: item[0]))
        return (
            f"{joinpoint.__module__}.{joinpoint.__qualname__}:"
            f"args={args!r}:kwargs={ordered_kwargs!r}"
        )
    except Exception as error:
        raise CacheKeyGenerationError() from error


@Order(0)
@Aspect()
class CacheAspect(IAspect):
    """Aspect that applies cacheable and cache eviction annotations."""

    _cache: ICache[object]

    def __init__(self, cache: ICache[object]) -> None:
        self._cache = cache

    @Around(_matches_sync)
    def around(
        self,
        joinpoint: Func,
        *args: object,
        **kwargs: object,
    ) -> object:
        evict = CacheEvict.get_or_none(joinpoint)
        if evict is not None:
            result = joinpoint(*args, **kwargs)
            self._cache.delete(_key_from_call(joinpoint, evict.key, args, kwargs))
            return result

        cacheable = Cacheable.get(joinpoint)
        key = _key_from_call(joinpoint, cacheable.key, args, kwargs)
        cached = self._cache.get(key)
        if isinstance(cached, CacheHit):
            return cached.value

        result = joinpoint(*args, **kwargs)
        self._cache.set(key, result, ttl=cacheable.ttl)
        return result


@Order(0)
@AsyncAspect()
class AsyncCacheAspect(IAsyncAspect):
    """Async aspect that applies cacheable and cache eviction annotations."""

    _cache: ICache[object]

    def __init__(self, cache: ICache[object]) -> None:
        self._cache = cache

    @Around(_matches_async)
    async def around_async(
        self,
        joinpoint: AsyncFunc,
        *args: object,
        **kwargs: object,
    ) -> object:
        evict = CacheEvict.get_or_none(joinpoint)
        if evict is not None:
            result = await joinpoint(*args, **kwargs)
            await self._cache.delete_async(
                _key_from_call(joinpoint, evict.key, args, kwargs)
            )
            return result

        cacheable = Cacheable.get(joinpoint)
        key = _key_from_call(joinpoint, cacheable.key, args, kwargs)
        cached = await self._cache.get_async(key)
        if isinstance(cached, CacheHit):
            return cached.value

        result = await joinpoint(*args, **kwargs)
        await self._cache.set_async(key, result, ttl=cacheable.ttl)
        return result
