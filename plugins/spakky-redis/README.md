# Spakky Redis

[Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 Redis 캐시 백엔드 플러그인입니다.

## 설치

```bash
pip install spakky-redis
```

## 주요 기능

- **공유 캐시 백엔드**: `RedisCache[T]`는 값을 Redis에 저장하므로 여러 프로세스 인스턴스가 같은 항목을 볼 수 있습니다.
- **코어 계약 호환성**: `spakky-cache`의 동기/비동기 `ICache[T]` 경로를 구현합니다.
- **TTL 의미론**: 양수 TTL 값은 Redis millisecond expiry로 변환되며, 없는 키와 만료된 키는 `CacheMiss`를 반환합니다.
- **명시적 실패**: Redis 연결/설정 실패와 직렬화 실패는 Spakky 캐시 에러로 발생합니다.
- **범위 제한 clear**: `clear`는 Redis 데이터베이스 전체를 비우지 않고 설정된 prefix 아래의 키만 제거합니다.
- **운영 기능**: tag invalidation, Redis lock 기반 stampede protection, metrics snapshot, actuator health/info extension을 제공합니다.

## 빠른 시작

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

## 설정

`RedisCacheConfig`는 표준 Spakky `@Configuration` 패턴을 따르며 `SPAKKY_REDIS__` prefix를 가진 환경변수를 읽습니다.

| 환경변수 | 기본값 |
|----------------------|---------|
| `SPAKKY_REDIS__HOST` | `localhost` |
| `SPAKKY_REDIS__PORT` | `6379` |
| `SPAKKY_REDIS__DB` | `0` |
| `SPAKKY_REDIS__USERNAME` | unset |
| `SPAKKY_REDIS__PASSWORD` | unset |
| `SPAKKY_REDIS__USE_SSL` | `false` |
| `SPAKKY_REDIS__KEY_PREFIX` | `spakky:cache:` |
| `SPAKKY_REDIS__SOCKET_TIMEOUT` | `5.0` |

## 비동기 사용

```python
from spakky.cache import CacheHit
from spakky.plugins.redis import RedisCache

cache = RedisCache[int]()
await cache.set_async("answer", 42)

result = await cache.get_async("answer")
if isinstance(result, CacheHit):
    assert result.value == 42
```

## 계약 참고

`RedisCache`는 `spakky-cache` 애플리케이션 데이터 캐시 계약의 backend 구현입니다. 비즈니스 코드는 `ICache[T]`에 의존해야 하며, cache hit/miss 처리를 backend에 묶지 않습니다.

값은 pickle로 직렬화되어 `SPAKKY_REDIS__KEY_PREFIX` 아래에 저장됩니다. `clear()`와 `clear_async()`는 해당 prefix 아래의 키만 삭제합니다. Redis 실패, 예상하지 못한 응답 타입, 직렬화 실패는 cache miss로 취급하지 않고 Spakky 캐시 에러로 발생합니다.

`set_with_tags()` / `evict_tags()`는 Redis set 기반 tag index로 그룹 무효화를 처리합니다. `get_or_set()`은 Redis lock으로 동일 key miss population을 직렬화합니다. `write_through()`는 origin writer 성공 후 cache를 갱신하고, `write_behind()`는 cache 갱신 후 origin writer를 호출합니다. `metrics()`는 hit/miss/write/delete/clear/tag eviction/stampede wait counter를 반환하며, actuator가 로드되면 `RedisCacheHealthProbe`와 `RedisCacheMetricsInfoContributor`가 등록됩니다.

## 라이선스

MIT License
