# Application Data Cache

Spakky cache is a backend-neutral application data cache for service and use-case code. It is separate from `ApplicationContext` internal type, singleton, and context caches; it does not change how pods are discovered or injected.

Use `spakky-cache` when application code needs a consistent hit/miss contract for repeated reads, external calls, or expensive calculations. Use `spakky-redis` when those entries must be shared across process instances.

## Core Contract

`AbstractCache[T]` provides sync and async paths for `get`, `set`, `delete`, and `clear`. A missing key returns `CacheMiss`; it is not a framework error. A stored value returns `CacheHit[T]`.

```python
from datetime import timedelta

from spakky.cache import CacheHit, InMemoryCache

cache = InMemoryCache[str]()
cache.set("profile:42", "Ada", ttl=timedelta(minutes=5))

result = cache.get("profile:42")
if isinstance(result, CacheHit):
    print(result.value)
```

`ttl=None` stores an entry until explicit deletion or clear. Positive `int`, `float`, and `datetime.timedelta` values expire entries after that duration. Zero or negative TTL values raise `InvalidCacheTTLError`.

## Method Annotations

Load the `spakky-cache` plugin to register `InMemoryCache`, `CacheAspect`, and `AsyncCacheAspect`. Then annotate service methods with `@cacheable()` or `@cache_evict()`.

```python
from datetime import timedelta

from spakky.cache import cache_evict, cacheable
from spakky.core.stereotype.usecase import UseCase


@UseCase()
class ProfileService:
    @cacheable(key="profile:{0}", ttl=timedelta(minutes=5))
    def load_profile(self, user_id: str) -> str:
        return f"profile:{user_id}"

    @cache_evict(key="profile:{0}")
    def refresh_profile(self, user_id: str) -> None:
        ...
```

The default key is deterministic for the method module, qualified name, positional arguments, and sorted keyword arguments. Explicit `key` values are Python format strings evaluated against call arguments.

`@cacheable()` reads the cache before invoking the method and stores the result on a miss. `@cache_evict()` deletes the matching entry only after the annotated method succeeds. Backend failures propagate as Spakky cache errors and are not silently converted to misses.

## Redis Backend

`spakky-redis` provides `RedisCache[T]`, a `spakky-cache` backend that stores pickled values in Redis. Business code can depend on `AbstractCache[T]` and switch from `InMemoryCache` to `RedisCache` without changing hit/miss handling.

```python
from datetime import timedelta

from spakky.plugins.redis import RedisCache

cache = RedisCache[str]()
cache.set("profile:42", "Ada", ttl=timedelta(minutes=5))
```

`RedisCacheConfig` reads `SPAKKY_REDIS__HOST`, `SPAKKY_REDIS__PORT`, `SPAKKY_REDIS__DB`, `SPAKKY_REDIS__USERNAME`, `SPAKKY_REDIS__PASSWORD`, `SPAKKY_REDIS__USE_SSL`, and `SPAKKY_REDIS__KEY_PREFIX`. `clear()` and `clear_async()` delete only keys under the configured prefix.

## Non-goals

The current cache milestone does not provide distributed locks, cache stampede protection, tag or group invalidation, write-through/write-behind policies, or metrics/exporter integration.
