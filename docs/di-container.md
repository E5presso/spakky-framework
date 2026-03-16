# DI/IoC 컨테이너 가이드

이 문서는 Spakky Framework의 의존성 주입(DI) 및 제어 역전(IoC) 컨테이너를 설명합니다.

---

## 개요

Spakky의 IoC 컨테이너는 `ApplicationContext`입니다. Pod의 생명주기 관리, 의존성 해결, 서비스 조정을 담당합니다.

```python
from spakky.core.application.application_context import ApplicationContext
from spakky.core.application import SpakkyApplication

# 직접 사용
context = ApplicationContext()
context.add(UserService)
context.start()

# SpakkyApplication을 통한 부트스트랩
app = SpakkyApplication(ApplicationContext())
app.scan().start()
```

---

## Pod 등록

### 클래스 Pod

`@Pod` 데코레이터로 클래스를 등록합니다. 생성자 파라미터가 자동으로 의존성으로 인식됩니다.

```python
from spakky.core.pod.annotations.pod import Pod

@Pod()
class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository
```

### 함수 Pod (팩토리 메서드)

함수도 Pod로 등록할 수 있습니다. 반환 타입이 Pod의 타입이 됩니다.

```python
@Pod()
def create_connection_pool() -> ConnectionPool:
    return ConnectionPool(size=10)
```

### Configuration 패턴

관련 팩토리 메서드를 `@Configuration` 클래스로 그룹화합니다.

```python
from spakky.core.stereotype.configuration import Configuration

@Configuration()
class DatabaseConfig:
    @Pod()
    def connection_pool(self) -> ConnectionPool:
        return ConnectionPool(size=10)

    @Pod()
    def session_factory(self, pool: ConnectionPool) -> SessionFactory:
        return SessionFactory(pool)
```

---

## Pod 스코프

Pod의 생명주기를 결정하는 세 가지 스코프가 있습니다.

### SINGLETON (기본값)

애플리케이션 전체에서 하나의 인스턴스를 공유합니다.

```python
@Pod(scope=Pod.Scope.SINGLETON)
class UserService:
    ...
```

### PROTOTYPE

요청할 때마다 새 인스턴스를 생성합니다.

```python
@Pod(scope=Pod.Scope.PROTOTYPE)
class RequestHandler:
    ...
```

### CONTEXT

요청/컨텍스트 범위 내에서 인스턴스를 공유합니다. 웹 요청 처럼 요청 단위로 상태를 격리해야 할 때 사용합니다.

```python
@Pod(scope=Pod.Scope.CONTEXT)
class RequestContext:
    user_id: UUID | None = None
```

---

## 의존성 주입 규칙

### 생성자 주입

Spakky는 **생성자 주입**만 지원합니다. 생성자 파라미터의 타입 힌트를 기반으로 의존성을 해결합니다.

```python
@Pod()
class OrderService:
    def __init__(
        self,
        user_repo: UserRepository,      # 타입으로 해결
        order_repo: OrderRepository,    # 타입으로 해결
    ) -> None:
        self.user_repo = user_repo
        self.order_repo = order_repo
```

### 제약 사항

다음은 허용되지 않습니다:

```python
# ❌ 위치 전용 인자 금지
def __init__(self, repo: Repository, /): ...

# ❌ *args, **kwargs 금지
def __init__(self, *args, **kwargs): ...

# ❌ 함수 Pod에서 Optional 반환 타입 금지
@Pod()
def create_service() -> Service | None: ...  # 에러
```

### Optional 의존성

의존성이 선택적일 경우 `| None`을 사용합니다.

```python
@Pod()
class NotificationService:
    def __init__(
        self,
        email_sender: EmailSender,
        sms_sender: SmsSender | None = None,  # 없으면 None 주입
    ) -> None:
        self.email_sender = email_sender
        self.sms_sender = sms_sender
```

---

## 의존성 해결 우선순위

동일 타입의 여러 Pod가 있을 때, 다음 순서로 해결됩니다:

### 1. Qualifier로 명시적 지정

`Annotated`와 `Qualifier`를 사용하여 이름으로 특정 Pod를 지정합니다.

```python
from typing import Annotated
from spakky.core.pod.annotations.qualifier import Qualifier

@Pod(name="cache")
class CacheUserRepository(IUserRepository):
    ...

@Pod(name="database")
class DatabaseUserRepository(IUserRepository):
    ...

@Pod()
class UserService:
    def __init__(
        self,
        repository: Annotated[IUserRepository, Qualifier(lambda p: p.name == "cache")],
    ) -> None:
        self.repository = repository
```

### 2. Primary 지정

`@Primary`로 기본 선택 대상을 지정합니다.

```python
from spakky.core.pod.annotations.primary import Primary

@Pod()
@Primary()
class DefaultUserRepository(IUserRepository):
    ...

@Pod()
class CacheUserRepository(IUserRepository):
    ...

# Qualifier 없이 요청하면 Primary가 선택됨
@Pod()
class UserService:
    def __init__(self, repository: IUserRepository) -> None:
        self.repository = repository  # DefaultUserRepository
```

### 3. 단일 후보

타입에 해당하는 Pod가 하나뿐이면 자동 선택됩니다.

### 4. 해결 실패

- `NoSuchPodError` — 해당 타입의 Pod가 없음
- `NoUniquePodError` — 여러 후보가 있으나 구분 불가

---

## 순환 참조 감지

컨테이너는 의존성 체인에서 순환 참조를 감지합니다.

```python
@Pod()
class ServiceA:
    def __init__(self, b: ServiceB) -> None: ...

@Pod()
class ServiceB:
    def __init__(self, a: ServiceA) -> None: ...  # 순환!
```

순환 참조 발생 시 `CircularDependencyGraphDetectedError`가 발생하며, 의존성 경로를 표시합니다:

```
Circular dependency graph detected
Dependency path:
ServiceA
  └─> ServiceB
    └─> ServiceA (CIRCULAR!)
```

### 해결 방법

1. **설계 재검토** — 순환 의존성은 종종 설계 문제를 나타냅니다
2. **인터페이스 분리** — 공통 인터페이스를 추출하여 의존 방향 정리
3. **이벤트 기반 통신** — 직접 참조 대신 이벤트로 통신

---

## Pod 조회

### 타입으로 조회

```python
service = context.get(UserService)
```

### 이름으로 조회

```python
repo = context.get(IUserRepository, "cache")
```

---

## Lazy 초기화

`@Lazy`로 Pod 인스턴스화를 첫 사용 시점까지 지연합니다.

```python
from spakky.core.pod.annotations.lazy import Lazy

@Pod()
@Lazy()
class ExpensiveService:
    def __init__(self) -> None:
        # 무거운 초기화 작업
        self.connection = establish_connection()
```

---

## 순서 지정

`@Order`로 Pod 처리 순서를 지정합니다 (숫자가 낮을수록 우선).

```python
from spakky.core.pod.annotations.order import Order

@Pod()
@Order(1)
class FirstProcessor:
    ...

@Pod()
@Order(2)
class SecondProcessor:
    ...
```

---

## Tag로 그룹화

`@Tag`로 Pod를 그룹화하여 일괄 조회합니다.

```python
from spakky.core.pod.annotations.tag import Tag

VALIDATOR_TAG = Tag("validator")

@Pod()
@VALIDATOR_TAG
class EmailValidator:
    ...

@Pod()
@VALIDATOR_TAG
class PhoneValidator:
    ...

# 태그로 모든 validator 조회
validators = context.find(lambda pod: VALIDATOR_TAG in pod.tags)
```

---

## PostProcessor

Pod 인스턴스가 생성된 후 추가 처리를 수행하는 확장 포인트입니다.

```python
from spakky.core.pod.interfaces.post_processor import IPostProcessor

class LoggingPostProcessor(IPostProcessor):
    def post_process(self, pod: object) -> object:
        print(f"Pod created: {type(pod).__name__}")
        return pod
```

`ApplicationContext`에는 기본 PostProcessor들이 등록되어 있습니다:

- `AspectPostProcessor` — AOP 프록시 적용
- `ApplicationContextAwareProcessor` — 컨텍스트 주입
- `ServicePostProcessor` — 서비스 생명주기 관리

---

## 컴포넌트 스캔

`SpakkyApplication.scan()`으로 패키지 내 Pod를 자동 탐색합니다.

```python
from spakky.core.application import SpakkyApplication

app = SpakkyApplication(ApplicationContext())
app.scan()  # 호출자의 패키지 스캔
app.scan(path="myapp.services")  # 특정 패키지 스캔
app.scan(exclude={"myapp.tests"})  # 제외 패턴
```

---

## 생명주기 관리

```python
context = ApplicationContext()

# Pod 등록
context.add(UserService)
context.add(OrderService)

# 시작 - Singleton 초기화, 서비스 시작
context.start()

# 사용
service = context.get(UserService)

# 종료 - 서비스 정지, 리소스 정리
context.stop()
```


