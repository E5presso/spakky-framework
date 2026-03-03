---
applyTo: "**/aspects/**/*.py"
---

# AOP Aspect 규칙

이 규칙은 `aspects/` 경로 하위 모든 Python 파일에 자동 적용됩니다.

## Aspect 핵심 API

| 클래스 / 데코레이터 | Import Path | 용도 |
|------------------|------------|------|
| `@Aspect()` | `spakky.core.aop.aspect` | 동기 Aspect 클래스 등록 |
| `@AsyncAspect()` | `spakky.core.aop.aspect` | 비동기 Aspect 클래스 등록 |
| `IAspect` | `spakky.core.aop.interfaces.aspect` | 동기 Aspect 인터페이스 |
| `IAsyncAspect` | `spakky.core.aop.interfaces.aspect` | 비동기 Aspect 인터페이스 |
| `@Before` | `spakky.core.aop.pointcut` | 메서드 실행 전 어드바이스 |
| `@After` | `spakky.core.aop.pointcut` | 메서드 실행 후 어드바이스 (항상) |
| `@Around` | `spakky.core.aop.pointcut` | 메서드 실행 전후 감쌈 |
| `@AfterReturning` | `spakky.core.aop.pointcut` | 정상 반환 후 어드바이스 |
| `@AfterRaising` | `spakky.core.aop.pointcut` | 예외 발생 후 어드바이스 |
| `@Order(n)` | `spakky.core.pod.annotations.order` | Aspect 실행 순서 (낮을수록 먼저) |

## 구조 패턴

동기와 비동기 버전을 **항상 쌍으로** 구현해야 합니다:

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
    """Async aspect for ..."""

    @Around(lambda x: MyAnnotation.exists(x) and iscoroutinefunction(x))
    async def around_async(
        self, joinpoint: AsyncFunc, *args: Any, **kwargs: Any
    ) -> Any:
        """..."""
        # pre-processing
        result = await joinpoint(*args, **kwargs)
        # post-processing
        return result


@Order(0)
@Aspect()
class MyAspect(IAspect):
    """Sync aspect for ..."""

    @Around(lambda x: MyAnnotation.exists(x) and not iscoroutinefunction(x))
    def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
        """..."""
        # pre-processing
        result = joinpoint(*args, **kwargs)
        # post-processing
        return result
```

## Annotation 패턴

Aspect를 트리거하는 어노테이션은 같은 파일에 정의합니다:

```python
from dataclasses import dataclass, field
from spakky.core.common.annotation import FunctionAnnotation

@dataclass
class MyAnnotation(FunctionAnnotation):
    """Annotation for enabling ..."""

    some_option: bool = True
    """Description of the option."""
```

## 포인트컷 (Pointcut) 규칙

- `@Around`: 반환값 제어가 필요한 경우 (가장 일반적)
- `@Before`: 사전 검증, 파라미터 변환
- `@After`: 정리(cleanup) 작업 (성공/실패 무관)
- `@AfterReturning`: 반환값 변환, 캐시 갱신
- `@AfterRaising`: 에러 변환, 재시도 로직

**포인트컷 조건 함수**: `iscoroutinefunction(x)` 조건으로 동기/비동기를 분리합니다.

## `@Order` 규칙

- 낮은 값 = 먼저 실행 (외부 래퍼)
- 높은 값 = 나중에 실행 (내부 래퍼)
- 기본값: `sys.maxsize` (가장 늦게)
- `@Logging()` Aspect는 `@Order(0)` — 가장 먼저 실행

## main.py 등록

Aspect 클래스는 플러그인의 `initialize` 함수에서 컨테이너에 등록합니다:

```python
from spakky.core.application.application import SpakkyApplication
from spakky.mypackage.aspects.my_aspect import AsyncMyAspect, MyAspect

def initialize(app: SpakkyApplication) -> None:
    app.add(AsyncMyAspect)
    app.add(MyAspect)
```

## 금지 사항

- `Any` 타입 사용 시 반드시 인라인 주석으로 사유 명시 (불가피한 경우만)
- 동기 전용 또는 비동기 전용으로만 구현하지 말 것 — **항상 쌍으로**
- Aspect 내에서 side effect(DB 쓰기, 외부 API 호출) 직접 수행 금지 — 의존성 주입으로 처리
