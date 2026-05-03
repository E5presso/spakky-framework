# Spakky Redis

Redis cache backend plugin for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-redis
```

## Features

- **Shared cache backend**: `RedisCache[T]` stores values in Redis so multiple process instances can observe the same entries.
- **Core contract compatibility**: Implements `spakky-cache` sync and async `ICache[T]` paths.
- **TTL semantics**: Positive TTL values are translated into Redis millisecond expiry; missing and expired keys return `CacheMiss`.
- **Loud failures**: Redis connection/configuration failures and serialization failures are raised as Spakky cache errors.
- **Scoped clear**: `clear` removes keys under the configured prefix instead of flushing the Redis database.

## Quick Start

```python
from datetime import timedelta

from spakky.cache import CacheHit
from spakky.plugins.redis import RedisCache

cache = RedisCache[str]()
cache.set("profile:42", "Ada", ttl=timedelta(minutes=5))

result = cache.get("profile:42")
if isinstance(result, CacheHit):
    print(result.value)
```

## Configuration

`RedisCacheConfig` follows the standard Spakky `@Configuration` pattern and reads environment variables with the `SPAKKY_REDIS__` prefix.

| Environment variable | Default |
|----------------------|---------|
| `SPAKKY_REDIS__HOST` | `localhost` |
| `SPAKKY_REDIS__PORT` | `6379` |
| `SPAKKY_REDIS__DB` | `0` |
| `SPAKKY_REDIS__USERNAME` | unset |
| `SPAKKY_REDIS__PASSWORD` | unset |
| `SPAKKY_REDIS__USE_SSL` | `false` |
| `SPAKKY_REDIS__KEY_PREFIX` | `spakky:cache:` |
| `SPAKKY_REDIS__SOCKET_TIMEOUT` | `5.0` |

## Async Usage

```python
from spakky.cache import CacheHit
from spakky.plugins.redis import RedisCache

cache = RedisCache[int]()
await cache.set_async("answer", 42)

result = await cache.get_async("answer")
if isinstance(result, CacheHit):
    assert result.value == 42
```

## Contract Notes

`RedisCache` is a backend implementation of the `spakky-cache` application data cache contract. Business code should depend on `ICache[T]` and can switch between `InMemoryCache` and `RedisCache` without changing cache hit/miss handling.

Values are serialized with pickle and stored under `SPAKKY_REDIS__KEY_PREFIX`. `clear()` and `clear_async()` delete only keys under that prefix. Redis failures, unexpected response types, and serialization failures are raised as Spakky cache errors instead of being treated as cache misses.

This plugin does not add distributed locks, cache stampede protection, tag invalidation, write-through/write-behind policies, or metrics exporters.

## License

MIT License
