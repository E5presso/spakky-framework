---
paths:
  - "**/aspects/**/*.py"
---

# AOP Aspect 규칙

## 구조 패턴 (동기+비동기 쌍 필수)

```python
from inspect import iscoroutinefunction
from typing import Any
from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.aop.pointcut import Around
from spakky.core.common.types import AsyncFunc, Func
from spakky.core.pod.annotations.order import Order

@Order(0)
@AsyncAspect()
class AsyncMyAspect(IAsyncAspect):
    @Around(lambda x: MyAnnotation.exists(x) and iscoroutinefunction(x))
    async def around(self, joinpoint: AsyncFunc, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        return await joinpoint(*args, **kwargs)

@Order(0)
@Aspect()
class MyAspect(IAspect):
    @Around(lambda x: MyAnnotation.exists(x) and not iscoroutinefunction(x))
    def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        return joinpoint(*args, **kwargs)
```

## Annotation 패턴

```python
from dataclasses import dataclass
from spakky.core.common.annotation import FunctionAnnotation

@dataclass
class MyAnnotation(FunctionAnnotation):
    some_option: bool = True
```

## 포인트컷 선택

| 데코레이터 | 사용 시점 |
|-----------|---------|
| `@Around` | 반환값 제어 (가장 일반적) |
| `@Before` | 사전 검증, 파라미터 변환 |
| `@After` | 성공/실패 무관 정리 |
| `@AfterReturning` | 반환값 변환, 캐시 갱신 |
| `@AfterRaising` | 에러 변환, 재시도 |

## `@Order` 규칙

낮은 값 = 외부 래퍼(먼저 실행). 기본값: `sys.maxsize`. `@logged()` → `@Order(0)`.

## 금지 사항

- 동기 전용 또는 비동기 전용 — **항상 쌍으로**
- Aspect에서 직접 DB 쓰기/외부 API 호출 금지 — 의존성 주입으로 처리
