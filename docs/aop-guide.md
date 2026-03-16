# AOP (관점 지향 프로그래밍) 가이드

이 문서는 Spakky Framework의 AOP 시스템을 설명합니다.

---

## 개요

AOP는 로깅, 트랜잭션, 보안 같은 **횡단 관심사**를 비즈니스 로직과 분리하여 모듈화합니다. Spakky는 런타임 프록시 기반 AOP를 제공합니다.

---

## 핵심 개념

### Aspect

횡단 관심사를 구현하는 Pod. `@Aspect` (동기) 또는 `@AsyncAspect` (비동기) 데코레이터로 표시합니다.

### Advice

Aspect가 특정 시점에 실행하는 코드:

- **Before** — 대상 메서드 실행 전
- **AfterReturning** — 메서드 정상 반환 후
- **AfterRaising** — 메서드 예외 발생 후
- **After** — 메서드 실행 후 (결과와 무관)
- **Around** — 메서드 실행을 감싸서 완전히 제어

### Pointcut

Advice가 적용될 메서드를 선택하는 조건자 함수. `Callable[[Func], bool]` 타입입니다.

### JoinPoint

Aspect가 개입하는 프로그램 실행 지점. Around advice에서 대상 메서드를 호출할 때 사용합니다.

---

## 동기 Aspect 작성

`@Aspect`와 `IAspect` 인터페이스를 사용합니다.

```python
from spakky.core.aop.aspect import Aspect
from spakky.core.aop.interfaces.aspect import IAspect
from spakky.core.aop.pointcut import Before, After, Around, AfterReturning, AfterRaising
from spakky.core.common.types import Func
from typing import Any

# Pointcut 함수 정의
def is_service_method(method: Func) -> bool:
    """서비스 메서드인지 판별"""
    return hasattr(method, "__service__")

@Aspect()
class AuditAspect(IAspect):
    """감사 로깅 Aspect"""

    @Before(pointcut=is_service_method)
    def before(self, *args: Any, **kwargs: Any) -> None:
        print(f"메서드 호출됨: args={args}, kwargs={kwargs}")

    @AfterReturning(pointcut=is_service_method)
    def after_returning(self, result: Any) -> None:
        print(f"반환값: {result}")

    @AfterRaising(pointcut=is_service_method)
    def after_raising(self, error: Exception) -> None:
        print(f"예외 발생: {error}")

    @After(pointcut=is_service_method)
    def after(self) -> None:
        print("메서드 완료")

    @Around(pointcut=is_service_method)
    def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
        print("실행 전")
        result = joinpoint(*args, **kwargs)  # 대상 메서드 호출
        print("실행 후")
        return result
```

---

## 비동기 Aspect 작성

`@AsyncAspect`와 `IAsyncAspect` 인터페이스를 사용합니다.

```python
from spakky.core.aop.aspect import AsyncAspect
from spakky.core.aop.interfaces.aspect import IAsyncAspect
from spakky.core.aop.pointcut import Before, Around
from spakky.core.common.types import AsyncFunc
from typing import Any

def is_async_handler(method: AsyncFunc) -> bool:
    return hasattr(method, "__handler__")

@AsyncAspect()
class AsyncTimingAspect(IAsyncAspect):
    """비동기 메서드 실행 시간 측정"""

    @Before(pointcut=is_async_handler)
    async def before_async(self, *args: Any, **kwargs: Any) -> None:
        print("비동기 메서드 시작")

    @Around(pointcut=is_async_handler)
    async def around_async(
        self, joinpoint: AsyncFunc, *args: Any, **kwargs: Any
    ) -> Any:
        import time
        start = time.perf_counter()
        result = await joinpoint(*args, **kwargs)
        elapsed = time.perf_counter() - start
        print(f"실행 시간: {elapsed:.3f}초")
        return result
```

---

## Pointcut 패턴

### 어노테이션 기반 Pointcut

가장 일반적인 패턴. 특정 어노테이션이 있는 메서드만 선택합니다.

```python
from spakky.core.common.annotation import FunctionAnnotation
from dataclasses import dataclass

@dataclass
class Cacheable(FunctionAnnotation):
    """캐싱 대상 메서드 표시"""
    ttl: int = 300  # 초

# Pointcut: @Cacheable이 있는 메서드
@Around(pointcut=lambda x: Cacheable.exists(x))
def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
    annotation = Cacheable.get(joinpoint)
    # annotation.ttl 사용 가능
    ...
```

### 동기/비동기 구분

```python
from inspect import iscoroutinefunction

# 동기 메서드만
@Around(pointcut=lambda x: MyAnnotation.exists(x) and not iscoroutinefunction(x))
def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
    ...

# 비동기 메서드만
@Around(pointcut=lambda x: MyAnnotation.exists(x) and iscoroutinefunction(x))
async def around_async(self, joinpoint: AsyncFunc, *args: Any, **kwargs: Any) -> Any:
    ...
```

### 클래스 타입 기반 Pointcut

```python
# 특정 클래스 메서드만
@Around(pointcut=lambda x: hasattr(x, "__self__") and isinstance(x.__self__, IService))
def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
    ...
```

---

## 내장 Aspect

### @Logging

메서드 호출, 인자, 반환값, 실행 시간을 자동 로깅합니다. 민감 데이터 마스킹을 지원합니다.

```python
from spakky.plugins.logging import Logging

class UserService:
    @Logging(enable_masking=True, masking_keys=["password", "token"])
    async def create_user(self, name: str, password: str) -> User:
        ...
```

로그 출력 예시:

```
[AsyncLoggingAspect] UserService.create_user(name='john', password='******') returned User(id=123) (0.05s)
```

### @Transactional

메서드를 트랜잭션 경계로 감쌉니다. 예외 발생 시 롤백, 정상 완료 시 커밋합니다.
인자가 없는 어노테이션이므로 `@Transactional()`과 `@transactional` shorthand를 모두 사용할 수 있습니다.

```python
from spakky.data.aspects.transactional import transactional

class OrderUseCase:
    @transactional
    async def place_order(self, command: PlaceOrderCommand) -> Order:
        # 이 메서드 내 모든 DB 작업이 하나의 트랜잭션으로 묶임
        order = Order.create(command)
        await self.repository.save(order)
        return order
```

---

## Aspect 순서 지정

`@Order`로 여러 Aspect의 실행 순서를 제어합니다. 숫자가 낮을수록 먼저 실행됩니다.

```python
from spakky.core.pod.annotations.order import Order

@Order(0)  # 가장 먼저 (외곽)
@AsyncAspect()
class TransactionAspect(IAsyncAspect):
    ...

@Order(1)  # 그 다음 (안쪽)
@AsyncAspect()
class LoggingAspect(IAsyncAspect):
    ...
```

실행 순서 (Around의 경우):

```
TransactionAspect.around_async 시작
  └─ LoggingAspect.around_async 시작
       └─ 실제 메서드 실행
     LoggingAspect.around_async 종료
TransactionAspect.around_async 종료
```

---

## Advice 실행 흐름

### 정상 실행

```
Before
  └─ Around (joinpoint 호출 전)
       └─ 대상 메서드 실행
     Around (joinpoint 호출 후)
AfterReturning
After
```

### 예외 발생

```
Before
  └─ Around (joinpoint 호출 전)
       └─ 대상 메서드에서 예외 발생 ❌
AfterRaising
After
(예외 전파)
```

---

## Around Advice 패턴

### 기본 래핑

```python
@Around(pointcut=is_target)
def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
    # 전처리
    result = joinpoint(*args, **kwargs)  # 반드시 호출!
    # 후처리
    return result  # 반드시 반환!
```

### 실행 건너뛰기 (조건부)

```python
@Around(pointcut=is_target)
def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
    if self.should_skip(args, kwargs):
        return None  # joinpoint 호출하지 않음
    return joinpoint(*args, **kwargs)
```

### 결과 변환

```python
@Around(pointcut=is_target)
def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
    result = joinpoint(*args, **kwargs)
    return self.transform(result)
```

### 예외 처리/변환

```python
@Around(pointcut=is_target)
def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
    try:
        return joinpoint(*args, **kwargs)
    except InternalError as e:
        raise PublicError(str(e)) from e
```

### 재시도 로직

```python
@Around(pointcut=is_target)
def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
    for attempt in range(3):
        try:
            return joinpoint(*args, **kwargs)
        except RetryableError:
            if attempt == 2:
                raise
            time.sleep(1)
```

---

## 주의사항

### 프록시 기반 제한

Spakky AOP는 런타임 프록시 방식입니다. 다음 제한이 있습니다:

1. **자기 호출 불가** — 같은 객체 내에서 `self.method()` 호출 시 Aspect가 적용되지 않음
2. **private 메서드** — `_private` 메서드는 외부에서 호출해도 Aspect 적용됨
3. **final 클래스** — 프록시 생성이 불가능한 경우 Aspect 적용 불가

### Around에서 joinpoint 호출 필수

Around advice에서 `joinpoint`를 호출하지 않으면 대상 메서드가 실행되지 않습니다. 의도적으로 건너뛰는 경우가 아니면 반드시 호출하세요.

```python
# ❌ 잘못된 예 - joinpoint 미호출
@Around(pointcut=is_target)
def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
    print("로깅만 하고 실제 메서드는 실행 안 됨!")
    return None

# ✅ 올바른 예
@Around(pointcut=is_target)
def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
    print("로깅")
    return joinpoint(*args, **kwargs)  # 반드시 호출
```

### 반환값 전달 필수

Around advice에서 `joinpoint()` 결과를 반환하지 않으면 호출자가 `None`을 받습니다.

```python
# ❌ 잘못된 예 - 반환값 누락
@Around(pointcut=is_target)
def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
    result = joinpoint(*args, **kwargs)
    # return 없음 → 호출자는 None 받음

# ✅ 올바른 예
@Around(pointcut=is_target)
def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
    result = joinpoint(*args, **kwargs)
    return result
```
