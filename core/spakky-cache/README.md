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

## License

MIT License
