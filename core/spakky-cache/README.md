# Spakky Cache

Backend-neutral application data cache contracts for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-cache
```

## Features

- **Typed cache results**: `CacheHit[T]` and `CacheMiss` represent hit and miss outcomes without backend-specific exceptions.
- **Sync and async contracts**: `AbstractCache[T]` defines `get`, `set`, `delete`, `clear` and async equivalents.
- **TTL semantics**: Positive TTL values expire entries deterministically; missing and expired entries are misses.
- **In-memory backend**: `InMemoryCache[T]` is suitable for local development, tests, and single-process usage.
- **AOP method caching**: `@cacheable()` and `@cache_evict()` apply cache hit/miss and eviction behavior without manual plumbing.
- **Application data scope**: This package does not expose or mutate `ApplicationContext` internal caches.

## Quick Start

```python
from datetime import timedelta

from spakky.cache import CacheHit, InMemoryCache

cache = InMemoryCache[str]()
cache.set("profile:42", "Ada", ttl=timedelta(minutes=5))

result = cache.get("profile:42")
if isinstance(result, CacheHit):
    print(result.value)
```

## Annotation Usage

Load the `spakky-cache` plugin, then annotate service methods. The plugin registers `InMemoryCache`, `CacheAspect`, and `AsyncCacheAspect` so sync and async methods are handled through Spakky AOP.

```python
from datetime import timedelta

from spakky.cache import cache_evict, cacheable
from spakky.core.stereotype.usecase import UseCase


@UseCase()
class ProfileService:
    def __init__(self) -> None:
        self.calls = 0

    @cacheable(key="profile:{0}", ttl=timedelta(minutes=5))
    def load_profile(self, user_id: str) -> str:
        self.calls += 1
        return f"profile:{user_id}"

    @cache_evict(key="profile:{0}")
    def refresh_profile(self, user_id: str) -> None:
        ...
```

The default key is derived from the method module, qualified name, positional arguments, and sorted keyword arguments. Explicit `key` values are Python format strings evaluated against method call arguments. Invalid key formatting raises `CacheKeyGenerationError`. Backend failures are not swallowed; cache errors propagate loudly.

`@cache_evict()` deletes the matching entry only after the annotated method succeeds. Failed method calls leave existing entries untouched so a failed refresh does not erase the last known cached value.

## Async Usage

```python
from spakky.cache import CacheHit, InMemoryCache

cache = InMemoryCache[int]()
await cache.set_async("answer", 42)

result = await cache.get_async("answer")
if isinstance(result, CacheHit):
    assert result.value == 42
```

## TTL Rules

`ttl=None` stores an entry until explicit deletion or clear. Positive `float`, `int`, or `datetime.timedelta` values expire entries after that duration. Zero or negative TTL values raise `InvalidCacheTTLError`.

The in-memory backend deletes expired entries when they are observed. It is deterministic for one process and does not provide distributed invalidation, stampede protection, or tag-based eviction.

Cache eviction annotations remove a single matching entry only after the annotated method succeeds.

## Scope

`spakky-cache` is an application data cache abstraction. It is separate from `ApplicationContext` internal type, singleton, and context caches. Distributed locks, cache stampede protection, tag invalidation, write-through/write-behind policies, and metrics exporters are outside the current contract.

## License

MIT License
