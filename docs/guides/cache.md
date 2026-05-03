# 애플리케이션 데이터 캐시

Spakky 캐시는 서비스와 유스케이스 코드에서 사용하는 백엔드 중립 애플리케이션 데이터 캐시입니다. `ApplicationContext` 내부의 타입 캐시, 싱글톤 캐시, 컨텍스트 캐시와는 별개이며 Pod 발견이나 주입 방식은 바꾸지 않습니다.

반복 조회, 외부 호출, 비용이 큰 계산 결과에 대해 일관된 hit/miss 계약이 필요하면 `spakky-cache`를 사용합니다. 캐시 항목을 여러 프로세스 인스턴스가 공유해야 하면 `spakky-redis`를 사용합니다.

## 코어 계약

`ICache[T]`는 `get`, `set`, `delete`, `clear`의 동기/비동기 경로를 모두 제공합니다. 키가 없으면 `CacheMiss`를 반환하며, 이는 프레임워크 에러가 아닙니다. 저장된 값이 있으면 `CacheHit[T]`를 반환합니다.

```python
from datetime import timedelta

from spakky.cache import CacheHit, InMemoryCache

cache = InMemoryCache[str]()
cache.set("profile:42", "Ada", ttl=timedelta(minutes=5))

result = cache.get("profile:42")
if isinstance(result, CacheHit):
    print(result.value)
```

`ttl=None`은 명시적으로 삭제하거나 전체 삭제하기 전까지 항목을 보존합니다. 양수 `int`, `float`, `datetime.timedelta` 값은 해당 시간이 지난 뒤 항목을 만료시킵니다. 0 이하 TTL 값은 `InvalidCacheTTLError`를 발생시킵니다.

## 메서드 어노테이션

`spakky-cache` 플러그인을 로드하면 `InMemoryCache`, `CacheAspect`, `AsyncCacheAspect`가 등록됩니다. 이후 서비스 메서드에 `@cacheable()` 또는 `@cache_evict()`를 붙이면 됩니다.

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

기본 키는 메서드 모듈, 정규화된 이름, 위치 인자, 정렬된 키워드 인자를 기반으로 결정적으로 생성됩니다. 명시적 `key` 값은 호출 인자에 대해 평가되는 Python format 문자열입니다. 키 포맷이 유효하지 않으면 `CacheKeyGenerationError`가 발생합니다.

`@cacheable()`은 메서드를 호출하기 전에 캐시를 읽고, miss이면 실행 결과를 저장합니다. `@cache_evict()`는 어노테이션이 붙은 메서드가 성공한 뒤에만 일치하는 항목을 삭제합니다. 백엔드 실패는 Spakky 캐시 에러로 전파되며, 조용히 miss로 바뀌지 않습니다.

## Redis 백엔드

`spakky-redis`는 Redis에 직렬화된 값을 저장하는 `spakky-cache` 백엔드인 `RedisCache[T]`를 제공합니다. 비즈니스 코드는 `ICache[T]`에 의존하면 되므로, hit/miss 처리 방식을 바꾸지 않고 `InMemoryCache`에서 `RedisCache`로 전환할 수 있습니다.

```python
from datetime import timedelta

from spakky.plugins.redis import RedisCache

cache = RedisCache[str]()
cache.set("profile:42", "Ada", ttl=timedelta(minutes=5))
```

`RedisCacheConfig`는 `SPAKKY_REDIS__HOST`, `SPAKKY_REDIS__PORT`, `SPAKKY_REDIS__DB`, `SPAKKY_REDIS__USERNAME`, `SPAKKY_REDIS__PASSWORD`, `SPAKKY_REDIS__USE_SSL`, `SPAKKY_REDIS__KEY_PREFIX`, `SPAKKY_REDIS__SOCKET_TIMEOUT`을 읽습니다. `clear()`와 `clear_async()`는 설정된 prefix 아래의 키만 삭제합니다.

## 범위 밖

현재 캐시 마일스톤은 분산 lock, cache stampede 보호, tag/group 단위 무효화, write-through/write-behind 정책, metrics/exporter 통합을 제공하지 않습니다.
