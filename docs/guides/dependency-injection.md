# DI & Pod

`@Pod`는 Spakky의 핵심 데코레이터입니다. Spring의 `@Bean`과 유사하게, 클래스를 DI 컨테이너에 등록합니다.

---

## 기본 사용법

### 클래스를 Pod로 등록

```python
from spakky.core.pod.annotations.pod import Pod

@Pod()
class UserRepository:
    def find_by_id(self, user_id: str) -> dict:
        return {"id": user_id, "name": "John"}
```

### 생성자 주입

`@Pod` 클래스의 생성자에 다른 Pod 타입을 선언하면 자동으로 주입됩니다.

```python
@Pod()
class UserService:
    _repo: UserRepository

    def __init__(self, repo: UserRepository) -> None:
        self._repo = repo

    def get_user(self, user_id: str) -> dict:
        return self._repo.find_by_id(user_id)
```

### 애플리케이션 시작

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
import apps  # @Pod가 정의된 패키지

app = (
    SpakkyApplication(ApplicationContext())
    .scan(apps)        # 패키지 내 @Pod 자동 검색
    .start()
)

# 타입으로 조회
service = app.container.get(type_=UserService)
user = service.get_user("user-123")
```

---

## 플러그인 로딩

플러그인이 필요한 경우 `.load_plugins()`를 호출합니다.

### 전체 로딩

`include`를 생략하면 설치된 **모든 플러그인**을 자동으로 로딩합니다.

```python
app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()
    .scan(apps)
    .start()
)
```

### 선택적 로딩

`include`에 `Plugin` 집합을 전달하면 **지정한 플러그인만** 로딩합니다.
각 플러그인 패키지는 `PLUGIN_NAME` 상수를 제공합니다.

```python
import spakky.plugins.celery
import spakky.plugins.sqlalchemy

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(
        include={
            spakky.plugins.celery.PLUGIN_NAME,
            spakky.plugins.sqlalchemy.PLUGIN_NAME,
        },
    )
    .scan(apps)
    .start()
)
```

### 플러그인 없이 시작

테스트 등에서 플러그인을 완전히 제외하려면 빈 `set`을 전달합니다.

```python
app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(include=set())
    .scan(apps)
    .start()
)
```

### 스캔 모듈 제외

`.scan()`에서 특정 모듈을 제외할 수 있습니다.

```python
from apps import legacy_module

app = (
    SpakkyApplication(ApplicationContext())
    .scan(apps, exclude={legacy_module})
    .start()
)
```

### 시작 진단와 manifest 재사용

시작 진단은 opt-in입니다. 활성화하면 `load_plugins`, `scan`,
`registration`, `post_processor_registration`, `instantiation`,
`post_processing`, `service_start` phase의 처리 개수와 성공/실패 상태를
`StartupReport`에서 읽을 수 있습니다.

```python
from pathlib import Path

app = (
    SpakkyApplication(ApplicationContext())
    .enable_startup_diagnostics()
    .enable_discovery_manifest(Path(".spakky/cache/discovery-manifest.json"))
    .load_plugins(include=set())
    .scan(apps)
    .start()
)

scan_record = app.startup_report.records[1]
manifest_decision = scan_record.diagnostic_details[0].value
```

DiscoveryManifest decision은 `miss`, `hit`, `stale_schema`, `stale_input` 중
하나입니다. `hit`은 저장된 scan 후보를 기존 등록 경로로 재사용하고, stale
또는 miss는 fresh discovery로 돌아갑니다. 이 기능은 container cache가 아니며
actuator endpoint나 exporter 연동을 자동으로 만들지 않습니다.

---

## 싱글톤

Pod는 기본적으로 **싱글톤**입니다. 같은 타입을 여러 번 조회해도 동일한 인스턴스를 반환합니다.

```python
service_a = app.container.get(type_=UserService)
service_b = app.container.get(type_=UserService)
assert service_a is service_b  # 같은 인스턴스
```

---

## 함수 기반 Pod

클래스 외에도 함수를 Pod로 등록할 수 있습니다. 설정값이나 외부 라이브러리 인스턴스를 제공할 때 유용합니다.

```python
@Pod()
def get_database_url() -> str:
    return "postgresql://localhost/mydb"

@Pod(name="api")
def get_api() -> FastAPI:
    return FastAPI(debug=True)
```

함수 파라미터도 클래스 생성자와 동일하게 **자동 주입**됩니다. 반환 타입이 Pod의 타입이 됩니다.

```python
@Pod()
def get_engine(database_url: str) -> Engine:
    return create_engine(database_url)
```

---

## 고급 기능

### 복수 구현체 선택

같은 interface나 port를 구현하는 Pod가 여러 개 등록되면 단수 주입은
명시적인 선택 정책을 따릅니다. 우선순위는 `Qualifier`, 명시 name,
`ApplicationContext.bind(PodBinding(...))`, `@Primary`, legacy parameter name
fallback 순서입니다. 이 순서로도 하나를 고를 수 없으면 컨테이너는 임의의
후보를 선택하지 않고 `NoUniquePodError`를 발생시킵니다.

Application config에서 선택 정책을 관리하려면 binding을 등록합니다.

```python
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.binding import PodBinding

class IEmailSender:
    def send(self, to: str, body: str) -> None: ...

@Pod(name="smtp")
class SmtpEmailSender(IEmailSender):
    def send(self, to: str, body: str) -> None: ...

@Pod(name="console")
class ConsoleEmailSender(IEmailSender):
    def send(self, to: str, body: str) -> None: ...

context = ApplicationContext()
context.bind(PodBinding(interface=IEmailSender, implementation_name="smtp"))

app = SpakkyApplication(context).scan(apps).start()
sender = app.container.get(IEmailSender)  # SmtpEmailSender
```

간단한 경우에는 `context.bind_to_name(IEmailSender, "smtp")` 또는
`context.bind_to_type(IEmailSender, SmtpEmailSender)`를 사용할 수 있습니다.
Binding은 Pod 등록 전에도 선언할 수 있으므로, 플러그인 자동 로딩 흐름을
유지하면서 application config만으로 단수 구현체 선택을 제어할 수 있습니다.

### Collection 주입

여러 구현체를 모두 사용해야 하면 단수 타입 대신 collection 타입을 선언합니다.
Collection 주입은 단수 선택 정책을 적용하지 않고, 매칭되는 모든 후보를 Pod
name 기준의 안정적인 순서로 주입합니다.

```python
@Pod()
class NotificationFanout:
    def __init__(
        self,
        senders: list[IEmailSender],
        sender_by_name: dict[str, IEmailSender],
    ) -> None:
        self.senders = senders
        self.smtp = sender_by_name["smtp"]
```

지원 타입은 `list[T]`, `tuple[T, ...]`, `dict[str, T]`입니다. Qualifier를
붙이면 collection에 들어갈 후보 전체를 필터링할 수 있습니다.

```python
from typing import Annotated
from spakky.core.pod.annotations.qualifier import Qualifier

@Pod()
class PrimaryFanout:
    def __init__(
        self,
        senders: Annotated[
            list[IEmailSender],
            Qualifier(lambda p: p.name.startswith("smtp")),
        ],
    ) -> None:
        self.senders = senders
```

`contains(type_)`는 해당 타입 후보가 등록되어 있는지만 확인합니다. 후보가
둘 이상이라 단수 resolution이 모호해도 `contains(type_)`는 `True`일 수
있으며, 실제 단수 선택 가능성은 `get(type_)` 또는 생성자 주입 시점에
판정됩니다.

### @Qualifier — 같은 타입의 Pod 구분

같은 인터페이스를 구현하는 Pod가 여러 개 있을 때, `Annotated` 타입 힌트에 `Qualifier`를 넣어 선택 조건을 지정합니다.
`Qualifier`는 `Pod` 메타데이터를 받아 `bool`을 반환하는 **callable(selector)**을 인자로 받습니다.

```python
from typing import Annotated
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.annotations.qualifier import Qualifier

class IRepository:
    def get(self, id: str) -> dict: ...

@Pod()
class MySQLRepository(IRepository):
    def get(self, id: str) -> dict:
        return {"source": "mysql", "id": id}

@Pod()
class PostgreSQLRepository(IRepository):
    def get(self, id: str) -> dict:
        return {"source": "postgresql", "id": id}

@Pod()
class DataService:
    _repo: IRepository

    def __init__(
        self,
        repo: Annotated[
            IRepository,
            Qualifier(lambda p: p.type_ == MySQLRepository),
        ],
    ) -> None:
        self._repo = repo
```

여러 `Qualifier`를 중첩하면 **AND** 조건으로 동작합니다.

```python
@Pod()
class StrictService:
    def __init__(
        self,
        repo: Annotated[
            IRepository,
            Qualifier(lambda p: p.is_family_with(IRepository)),
            Qualifier(lambda p: p.type_ == MySQLRepository),
        ],
    ) -> None:
        self.repo = repo
```

### @Primary — 기본 Pod 지정

같은 타입이 여러 개일 때, `@Primary`가 붙은 Pod가 기본으로 선택됩니다.

```python
from spakky.core.pod.annotations.primary import Primary

@Pod()
@Primary()
class DefaultEmailSender:
    def send(self, to: str, body: str) -> None: ...

@Pod()
class DebugEmailSender:
    def send(self, to: str, body: str) -> None:
        print(f"[DEBUG] To: {to}, Body: {body}")
```

### @Lazy — 지연 초기화

처음 사용될 때까지 인스턴스 생성을 지연합니다.

```python
from spakky.core.pod.annotations.lazy import Lazy

@Pod()
@Lazy()
class HeavyService:
    def __init__(self) -> None:
        # 시작 시 바로 실행되지 않음
        self.connection = create_expensive_connection()
```

### @Tag — 메타데이터 태깅

`Tag`의 서브클래스를 정의하여 Pod에 메타데이터를 부여할 수 있습니다. 태그는 `ApplicationContext`의 태그 레지스트리에 자동 등록됩니다.

```python
from dataclasses import dataclass
from spakky.core.pod.annotations.tag import Tag

@dataclass(eq=False)
class NotificationTag(Tag):
    channel: str = ""

@NotificationTag(channel="email")
@Pod()
class EmailNotifier:
    pass

@NotificationTag(channel="slack")
@Pod()
class SlackNotifier:
    pass
```

등록된 태그는 `ApplicationContext`를 통해 조회할 수 있습니다.

```python
# 모든 태그 조회
all_tags = app.application_context.tags

# 조건으로 필터링
email_tags = app.application_context.list_tags(
    lambda t: isinstance(t, NotificationTag) and t.channel == "email"
)

# 특정 태그 존재 여부 확인
exists = app.application_context.contains_tag(NotificationTag(channel="email"))
```

---

## Stereotype 어노테이션

목적에 따라 의미를 부여하는 특화된 데코레이터들입니다. 내부적으로 `@Pod`와 동일하게 동작합니다.

```python
from spakky.core.stereotype.usecase import UseCase
from spakky.core.stereotype.controller import Controller
from spakky.core.stereotype.configuration import Configuration

@UseCase()
class CreateOrderUseCase:
    """비즈니스 로직 캡슐화"""
    pass

@Controller()
class OrderController:
    """프레젠테이션 레이어"""
    pass

@Configuration()
class AppConfig:
    """애플리케이션 설정"""
    pass
```
