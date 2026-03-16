# AOP (관점 지향 프로그래밍)

AOP를 사용하면 로깅, 트랜잭션, 인증 같은 **횡단 관심사**를 비즈니스 로직에서 분리할 수 있습니다.

---

## 핵심 개념

| 용어           | 설명                                           |
| -------------- | ---------------------------------------------- |
| **Aspect**     | 횡단 관심사를 구현한 클래스                    |
| **Advice**     | 실제 실행되는 코드 (Before, After, Around)     |
| **Pointcut**   | Advice가 적용될 조건 (어노테이션 존재 여부 등) |
| **Annotation** | 대상 메서드에 마킹하는 데코레이터              |

---

## 기본 사용법

### 1단계: 어노테이션 정의

대상 메서드에 붙일 어노테이션을 만듭니다.

```python
from spakky.core.common.annotation import FunctionAnnotation
from dataclasses import dataclass

@dataclass
class Log(FunctionAnnotation):
    """이 어노테이션이 붙은 메서드에 로깅을 적용"""
    pass
```

### 2단계: Aspect 구현

어노테이션이 존재하는 메서드에 대해 실행할 로직을 작성합니다.

```python
from typing import Any

from spakky.core.aop.aspect import Aspect
from spakky.core.aop.interfaces.aspect import IAspect
from spakky.core.aop.pointcut import Before, AfterReturning, AfterRaising, After, Around
from spakky.core.common.types import Func

@Aspect()
class LogAspect(IAspect):
    @Before(Log.exists)
    def before(self, *args: Any, **kwargs: Any) -> None:
        print(f"호출 시작: args={args}, kwargs={kwargs}")

    @AfterReturning(Log.exists)
    def after_returning(self, result: Any) -> None:
        print(f"반환값: {result}")

    @AfterRaising(Log.exists)
    def after_raising(self, error: Exception) -> None:
        print(f"예외 발생: {error}")

    @After(Log.exists)
    def after(self) -> None:
        print("호출 종료 (성공/실패 무관)")
```

### 3단계: 어노테이션 적용

비즈니스 로직 메서드에 어노테이션을 붙입니다.

```python
from spakky.core.pod.annotations.pod import Pod

@Pod()
class EchoService:
    @Log()
    def echo(self, message: str) -> str:
        return message

    @Log()
    def fail(self) -> None:
        raise ValueError("의도적 에러")
```

### 4단계: 실행

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
import apps

app = (
    SpakkyApplication(ApplicationContext())
    .scan(apps)
    .start()
)

service = app.container.get(type_=EchoService)

service.echo(message="Hello")
# 출력:
# 호출 시작: args=(), kwargs={'message': 'Hello'}
# 반환값: Hello
# 호출 종료 (성공/실패 무관)

service.fail()
# 출력:
# 호출 시작: args=(), kwargs={}
# 예외 발생: 의도적 에러
# 호출 종료 (성공/실패 무관)
```

---

## Advice 타입

### Before — 메서드 실행 전

```python
@Aspect()
class AuthAspect(IAspect):
    @Before(RequireAuth.exists)
    def before(self, *args: Any, **kwargs: Any) -> None:
        token = kwargs.get("token")
        if not token:
            raise PermissionError("인증 필요")
```

### AfterReturning — 정상 반환 후

```python
@Aspect()
class CacheAspect(IAspect):
    @AfterReturning(Cacheable.exists)
    def after_returning(self, result: Any) -> None:
        cache.set(result.id, result)
```

### AfterRaising — 예외 발생 후

```python
@Aspect()
class ErrorTrackingAspect(IAspect):
    @AfterRaising(Tracked.exists)
    def after_raising(self, error: Exception) -> None:
        error_tracker.report(error)
```

### After — 성공/실패 무관, 항상 실행

```python
@Aspect()
class CleanupAspect(IAspect):
    @After(NeedsCleanup.exists)
    def after(self) -> None:
        temp_files.clear()
```

### Around — 전체 흐름 제어

가장 유연한 Advice. 메서드 실행 전후를 모두 제어할 수 있습니다.

```python
@Aspect()
class TimingAspect(IAspect):
    @Around(Timed.exists)
    def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
        import time
        start = time.perf_counter()
        try:
            result = joinpoint(*args, **kwargs)
            return result
        finally:
            elapsed = time.perf_counter() - start
            print(f"{joinpoint.__name__}: {elapsed:.3f}s")
```

!!! warning "Around에서 joinpoint 호출 필수"
`joinpoint(*args, **kwargs)`를 호출하지 않으면 원래 메서드가 실행되지 않습니다.

---

## 비동기 지원

비동기 메서드를 인터셉트하려면 `AsyncAspect` + `IAsyncAspect`를 사용합니다.
메서드명은 `IAspect`와 동일하지만 **`_async` 접미사**가 붙습니다.

| IAspect (동기)      | IAsyncAspect (비동기)     |
| ------------------- | ------------------------- |
| `before()`          | `before_async()`          |
| `after_returning()` | `after_returning_async()` |
| `after_raising()`   | `after_raising_async()`   |
| `after()`           | `after_async()`           |
| `around()`          | `around_async()`          |

```python
from spakky.core.aop.aspect import AsyncAspect
from spakky.core.aop.interfaces.aspect import IAsyncAspect
from spakky.core.aop.pointcut import Around
from spakky.core.common.types import AsyncFunc

@AsyncAspect()
class AsyncTimingAspect(IAsyncAspect):
    @Around(Timed.exists)
    async def around_async(self, joinpoint: AsyncFunc, *args: Any, **kwargs: Any) -> Any:
        import time
        start = time.perf_counter()
        try:
            result = await joinpoint(*args, **kwargs)
            return result
        finally:
            elapsed = time.perf_counter() - start
            print(f"{joinpoint.__name__}: {elapsed:.3f}s")
```

동기/비동기 메서드를 모두 인터셉트하려면 **두 Aspect를 모두 정의**해야 합니다.

```python
@Aspect()
class SyncLogAspect(IAspect):
    @Before(Log.exists)
    def before(self, *args: Any, **kwargs: Any) -> None:
        print("sync before")

@AsyncAspect()
class AsyncLogAspect(IAsyncAspect):
    @Before(Log.exists)
    async def before_async(self, *args: Any, **kwargs: Any) -> None:
        print("async before")
```

---

## Pointcut 조건

Pointcut은 **어노테이션의 존재 여부를 검사하는 함수**입니다.

```python
@Aspect()
class MyAspect(IAspect):
    # 기본 패턴: 어노테이션.exists
    @Before(Log.exists)
    def before(self, *args: Any, **kwargs: Any) -> None: ...

    # 커스텀 조건도 가능 (inspect.iscoroutinefunction 활용)
    from inspect import iscoroutinefunction

    @Around(lambda x: Log.exists(x) and not iscoroutinefunction(x))
    def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
        return joinpoint(*args, **kwargs)
```
