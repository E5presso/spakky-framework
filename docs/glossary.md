# Spakky Framework 용어 사전

이 문서는 Spakky Framework에서 사용하는 핵심 용어를 정의합니다.

---

## 코어 개념

### Pod

컨테이너가 관리하는 컴포넌트 단위. `@Pod` 데코레이터로 클래스나 함수를 표시하면 `ApplicationContext`가 인스턴스 생명주기와 의존성 주입을 담당합니다.

```python
from spakky.core.pod.annotations.pod import Pod

@Pod()
class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository
```

**스코프 (Scope)**:

- `SINGLETON` — 애플리케이션 전체에서 하나의 인스턴스 공유 (기본값)
- `PROTOTYPE` — 요청할 때마다 새 인스턴스 생성
- `CONTEXT` — 요청/컨텍스트 범위 내에서 인스턴스 공유

### ApplicationContext

Pod 인스턴스와 생명주기를 관리하는 핵심 컨테이너. 의존성 주입, 서비스 시작/종료, 이벤트 루프 관리를 담당합니다.

```python
from spakky.core.application.application_context import ApplicationContext

context = ApplicationContext()
context.add(UserService)
context.start()
```

### SpakkyApplication

애플리케이션 부트스트랩 진입점. 컴포넌트 스캔, 플러그인 로딩, 컨테이너 설정을 위한 fluent API를 제공합니다.

```python
from spakky.core.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

app = SpakkyApplication(ApplicationContext())
app.scan()  # 현재 패키지의 Pod 자동 스캔
```

---

## Stereotype 데코레이터

Pod의 역할을 명시하는 특화된 데코레이터입니다. 기능적으로 `@Pod`와 동일하지만 의도를 명확히 합니다.

### @Configuration

팩토리 메서드를 포함하는 설정 클래스. 다른 Pod를 생성하는 `@Pod` 메서드를 그룹화합니다.

```python
from spakky.core.stereotype.configuration import Configuration
from spakky.core.pod.annotations.pod import Pod

@Configuration()
class DatabaseConfig:
    @Pod()
    def connection_pool(self) -> ConnectionPool:
        return ConnectionPool(size=10)
```

### @Controller

외부 요청을 처리하는 클래스 (HTTP, CLI 등).

```python
from spakky.core.stereotype.controller import Controller

@Controller()
class UserController:
    def __init__(self, service: UserService) -> None:
        self.service = service
```

### @UseCase

비즈니스 로직을 캡슐화하는 애플리케이션 서비스.

```python
from spakky.core.stereotype.usecase import UseCase

@UseCase()
class CreateUserUseCase:
    def execute(self, command: CreateUserCommand) -> User:
        ...
```

### @Repository

데이터 접근 계층. 영속성 저장소와의 상호작용을 추상화합니다.

```python
from spakky.data.stereotype.repository import Repository

@Repository()
class UserRepository:
    def find_by_id(self, id: UUID) -> User | None:
        ...
```

### @EventHandler

이벤트를 처리하는 클래스. `@on_event` 데코레이터와 함께 사용합니다.

```python
from spakky.event.stereotype.event_handler import EventHandler, on_event

@EventHandler()
class UserEventHandler:
    @on_event(UserCreatedEvent)
    async def handle(self, event: UserCreatedEvent) -> None:
        ...
```

---

## AOP (관점 지향 프로그래밍)

### Aspect

횡단 관심사 (로깅, 트랜잭션 등)를 모듈화하는 컴포넌트. `IAspect` 또는 `IAsyncAspect` 인터페이스를 구현합니다.

```python
from spakky.core.aop.aspect import Aspect
from spakky.core.aop.interfaces.aspect import IAspect

@Aspect()
class LoggingAspect(IAspect):
    def before(self, *args, **kwargs) -> None:
        print("Method called")
```

### Advice

Aspect가 특정 시점에 실행하는 액션:

- **Before** — 메서드 실행 전
- **AfterReturning** — 메서드 정상 반환 후
- **AfterRaising** — 메서드 예외 발생 후
- **After** — 메서드 실행 후 (결과와 무관)
- **Around** — 메서드 실행을 감싸서 제어

### Pointcut

Advice가 적용될 메서드를 선택하는 조건자 함수.

```python
from spakky.core.aop.pointcut import Around

def is_service_method(method) -> bool:
    return hasattr(method, "__service__")

@Around(pointcut=is_service_method)
def around(self, joinpoint, *args, **kwargs):
    return joinpoint(*args, **kwargs)
```

### JoinPoint

Aspect가 개입할 수 있는 프로그램 실행 지점. Around advice에서 다음 호출을 제어할 때 사용합니다.

---

## 도메인 모델 (spakky-domain)

### Entity

고유 식별자로 구분되는 도메인 객체. `AbstractEntity`를 상속합니다.

```python
from spakky.domain.models.entity import AbstractEntity

@mutable
class User(AbstractEntity[UUID]):
    name: str
    email: str
```

### ValueObject

식별자 없이 속성값으로만 동등성을 판단하는 불변 객체. `AbstractValueObject`를 상속합니다.

```python
from spakky.domain.models.value_object import AbstractValueObject

@immutable
class Email(AbstractValueObject):
    value: str
```

### AggregateRoot

일관성 경계를 관리하는 엔터티의 진입점. 도메인 이벤트를 수집하고 발행합니다. `AbstractAggregateRoot`를 상속합니다.

```python
from spakky.domain.models.aggregate_root import AbstractAggregateRoot

@mutable
class Order(AbstractAggregateRoot[UUID]):
    items: list[OrderItem]

    def add_item(self, item: OrderItem) -> None:
        self.items.append(item)
        self.add_event(ItemAddedEvent(order_id=self.id, item=item))
```

---

## 이벤트 시스템 (spakky-event)

### DomainEvent

하나의 바운디드 컨텍스트 내에서 발생하는 도메인 상태 변경. `AbstractDomainEvent`를 상속합니다.

```python
from spakky.domain.models.event import AbstractDomainEvent

@immutable
class UserCreatedEvent(AbstractDomainEvent):
    user_id: UUID
    email: str
```

### IntegrationEvent

바운디드 컨텍스트 간 또는 서비스 간 통신에 사용되는 이벤트. `AbstractIntegrationEvent`를 상속합니다.

```python
from spakky.domain.models.event import AbstractIntegrationEvent

@immutable
class OrderPlacedEvent(AbstractIntegrationEvent):
    order_id: UUID
    total_amount: Decimal
```

### EventPublisher

이벤트를 발행하는 인터페이스:

- `IDomainEventPublisher` — 동기 도메인 이벤트 발행
- `IAsyncDomainEventPublisher` — 비동기 도메인 이벤트 발행
- `IIntegrationEventPublisher` — 동기 통합 이벤트 발행
- `IAsyncIntegrationEventPublisher` — 비동기 통합 이벤트 발행

---

## 서비스 생명주기

### IService

시작/종료 생명주기를 가진 동기 서비스 인터페이스.

```python
from spakky.core.service.interfaces.service import IService

class BackgroundWorker(IService):
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

### IAsyncService

시작/종료 생명주기를 가진 비동기 서비스 인터페이스.

```python
from spakky.core.service.interfaces.service import IAsyncService

class AsyncWorker(IAsyncService):
    async def start_async(self) -> None: ...
    async def stop_async(self) -> None: ...
```

---

## 플러그인 시스템

### Plugin

프레임워크 확장을 식별하는 불변 객체. 이름으로 구분됩니다.

```python
from spakky.core.application.plugin import Plugin

FASTAPI_PLUGIN = Plugin(name="spakky-fastapi")
```

플러그인 로딩:

```python
app.load_plugins(include={FASTAPI_PLUGIN})
```

---

## 데이터 계층 (spakky-data)

### @Transactional

메서드에 트랜잭션 경계를 적용하는 Aspect.

### AggregateCollector

AggregateRoot에서 발생한 도메인 이벤트를 수집하여 트랜잭션 커밋 시 발행하는 컴포넌트.

---

## 어노테이션

### @Primary

동일 타입의 여러 Pod 중 기본 선택 대상으로 지정.

```python
@Pod()
@Primary()
class DefaultUserRepository(IUserRepository):
    ...
```

### @Qualifier

의존성 주입 시 특정 Pod를 이름으로 지정.

```python
@Pod(name="cache")
class CacheUserRepository(IUserRepository):
    ...

@Pod()
class UserService:
    def __init__(self, repository: Annotated[IUserRepository, Qualifier("cache")]) -> None:
        ...
```

### @Lazy

Pod 인스턴스화를 첫 사용 시점까지 지연.

### @Order

Pod 처리 순서를 지정 (숫자가 낮을수록 우선).

### @Tag

Pod를 태그로 그룹화하여 일괄 조회 가능.

---

## 에러 계층

### AbstractSpakkyFrameworkError

모든 Spakky 프레임워크 예외의 기반 클래스.

### PodAnnotationFailedError

Pod 어노테이션 처리 중 발생하는 예외.

### PodInstantiationFailedError

Pod 인스턴스 생성 중 발생하는 예외.
