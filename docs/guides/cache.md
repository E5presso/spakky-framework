# 애플리케이션 데이터 캐시

> `spakky-cache`의 backend-neutral cache 계약과 `spakky-redis` 운영 백엔드를 함께 사용하는 방법을 설명합니다.

Spakky 캐시는 서비스와 유스케이스 코드에서 사용하는 백엔드 중립 애플리케이션 데이터 캐시입니다. `ApplicationContext` 내부의 타입 캐시, 싱글톤 캐시, 컨텍스트 캐시와는 별개이며 Pod 발견이나 주입 방식은 바꾸지 않습니다.

반복 조회, 외부 호출, 비용이 큰 계산 결과에 대해 일관된 hit/miss 계약이 필요하면 `spakky-cache`를 사용합니다. 캐시 항목을 여러 프로세스 인스턴스가 공유해야 하면 `spakky-redis`를 사용합니다.

## 빠른 시작

애플리케이션 코드는 캐시 객체를 직접 만들지 않습니다. `spakky-cache`와 backend plugin을 로드한 뒤 서비스 메서드에 `@cacheable()` 또는 `@cache_evict()`를 붙이면, 캐시 Aspect가 등록된 `ICache` backend를 사용합니다.

```python
from datetime import timedelta

from spakky.cache import cache_evict, cacheable
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.application.plugin import Plugin
from spakky.core.stereotype.usecase import UseCase


@UseCase()
class ProfileService:
    @cacheable(key="profile:{0}", ttl=timedelta(minutes=5))
    def load_profile(self, user_id: str) -> str:
        return f"profile:{user_id}"

    @cache_evict(key="profile:{0}")
    def refresh_profile(self, user_id: str) -> None:
        ...


app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(
        include={
            Plugin(name="spakky-cache"),
            Plugin(name="spakky-redis"),
        }
    )
    .add(ProfileService)
    .start()
)

profiles = app.container.get(type_=ProfileService)
profiles.load_profile("42")
```

`spakky-cache` 플러그인은 `CacheAspect`, `AsyncCacheAspect`를 등록합니다. `spakky-redis`는 `RedisCacheConfig`, `RedisCache`, Redis actuator extension을 Pod로 등록하므로 서비스 코드는 backend 생성과 배선을 알 필요가 없습니다.

기본 키는 메서드 모듈, 정규화된 이름, 위치 인자, 정렬된 키워드 인자를 기반으로 결정적으로 생성됩니다. 명시적 `key` 값은 호출 인자에 대해 평가되는 Python format 문자열입니다. 키 포맷이 유효하지 않으면 `CacheKeyGenerationError`가 발생합니다.

`@cacheable()`은 메서드를 호출하기 전에 캐시를 읽고, miss이면 실행 결과를 저장합니다. `@cache_evict()`는 어노테이션이 붙은 메서드가 성공한 뒤에만 일치하는 항목을 삭제합니다. 백엔드 실패는 Spakky 캐시 에러로 전파되며, 조용히 miss로 바뀌지 않습니다.

## 코어 계약

`ICache[T]`는 `get`, `set`, `delete`, `clear`의 동기/비동기 경로를 모두 제공합니다. 키가 없으면 `CacheMiss`를 반환하며, 이는 프레임워크 에러가 아닙니다. 저장된 값이 있으면 `CacheHit[T]`를 반환합니다. Core package는 실제 저장소 backend를 직접 제공하지 않으며, 운영 backend는 `spakky-redis` 같은 backend plugin이 제공합니다.

`ttl=None`은 명시적으로 삭제하거나 전체 삭제하기 전까지 항목을 보존합니다. 양수 `int`, `float`, `datetime.timedelta` 값은 해당 시간이 지난 뒤 항목을 만료시킵니다. 0 이하 TTL 값은 `InvalidCacheTTLError`를 발생시킵니다.

## Redis 백엔드

`spakky-redis`는 Redis에 직렬화된 값을 저장하는 `spakky-cache` 백엔드인 `RedisCache[T]`를 제공합니다. 비즈니스 코드는 캐시 어노테이션 또는 `ICache[T]` 계약에 의존하면 되므로 cache hit/miss 처리 방식을 backend에 묶지 않습니다.

`RedisCacheConfig`는 `SPAKKY_REDIS__HOST`, `SPAKKY_REDIS__PORT`, `SPAKKY_REDIS__DB`, `SPAKKY_REDIS__USERNAME`, `SPAKKY_REDIS__PASSWORD`, `SPAKKY_REDIS__USE_SSL`, `SPAKKY_REDIS__KEY_PREFIX`, `SPAKKY_REDIS__SOCKET_TIMEOUT`을 읽습니다. `clear()`와 `clear_async()`는 설정된 prefix 아래의 키만 삭제합니다.

## 운영 기능

`@cacheable(tags=(...))`와 `@cache_evict(tags=(...))`는 backend가 `ITaggedCache`를 구현할 때 tag 기반 저장/무효화를 수행합니다. `RedisCache`는 tag index를 Redis set으로 유지하고 `evict_tags()` / `evict_tags_async()`를 제공합니다.

`RedisCache.get_or_set()`과 `get_or_set_async()`는 Redis lock으로 miss population을 직렬화하여 동일 key에 대한 cache stampede를 줄입니다. `metrics()`는 hit, miss, write, delete, clear, tag eviction, stampede wait counter를 반환하며, `spakky-actuator`가 함께 로드되면 Redis health와 metrics info contributor가 등록됩니다.

`write_through()` / `write_through_async()`는 origin writer가 성공한 뒤 cache를 갱신합니다. `write_behind()` / `write_behind_async()`는 cache를 먼저 갱신한 뒤 origin writer를 호출합니다.
