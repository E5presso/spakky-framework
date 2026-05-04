# Spakky Cache

[Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 백엔드 중립 애플리케이션 데이터 캐시 계약과 AOP 어노테이션입니다.

## 설치

```bash
pip install spakky-cache
```

## 주요 기능

- **타입화된 캐시 결과**: `CacheHit[T]`와 `CacheMiss`는 백엔드별 예외 없이 hit/miss 결과를 표현합니다.
- **동기/비동기 계약**: `ICache[T]`는 `get`, `set`, `delete`, `clear`와 비동기 대응 메서드를 정의합니다.
- **TTL 의미론**: 양수 TTL 값은 항목을 결정적으로 만료시키며, 없는 항목과 만료된 항목은 miss입니다.
- **AOP 메서드 캐싱**: `@cacheable()`과 `@cache_evict()`은 수동 배선 없이 cache hit/miss와 evict 동작을 적용합니다.
- **운영 backend 분리**: Core package는 저장소 backend를 등록하지 않으며, `spakky-redis` 같은 backend plugin이 `ICache[T]` 구현체를 제공합니다.
- **애플리케이션 데이터 범위**: 이 패키지는 `ApplicationContext` 내부 캐시를 노출하거나 변경하지 않습니다.

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

## 어노테이션 사용

`spakky-cache` 플러그인을 로드한 뒤 서비스 메서드에 어노테이션을 붙입니다. 이 플러그인은 `CacheAspect`, `AsyncCacheAspect`를 등록하며, 실제 저장소 backend는 `spakky-redis` 같은 plugin이 제공합니다.

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

기본 키는 메서드 모듈, 정규화된 이름, 위치 인자, 정렬된 키워드 인자에서 파생됩니다. 명시적 `key` 값은 메서드 호출 인자에 대해 평가되는 Python format 문자열입니다. 키 포맷이 유효하지 않으면 `CacheKeyGenerationError`가 발생합니다. 백엔드 실패는 삼키지 않고 캐시 에러로 전파합니다.

`@cache_evict()`은 어노테이션이 붙은 메서드가 성공한 뒤에만 일치하는 항목을 삭제합니다. 실패한 메서드 호출은 기존 항목을 건드리지 않으므로, refresh 실패가 마지막으로 알려진 캐시 값을 지우지 않습니다.

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

## TTL 규칙

`ttl=None`은 명시적 삭제 또는 전체 삭제 전까지 항목을 저장합니다. 양수 `float`, `int`, `datetime.timedelta` 값은 해당 시간이 지난 뒤 항목을 만료시킵니다. 0 이하 TTL 값은 `InvalidCacheTTLError`를 발생시킵니다.

캐시 evict 어노테이션은 어노테이션이 붙은 메서드가 성공한 뒤에만 일치하는 항목 하나를 제거합니다.

## 범위

`spakky-cache`는 애플리케이션 데이터 캐시 추상화입니다. `ApplicationContext` 내부의 타입 캐시, 싱글톤 캐시, 컨텍스트 캐시와는 별개입니다. Tag 기반 무효화, stampede 보호, write-through/write-behind, metrics는 core capability contract로 정의되며, `spakky-redis`가 Redis backend 구현을 제공합니다.

## 라이선스

MIT License
