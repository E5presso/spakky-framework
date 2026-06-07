# DI & Pod 심화

> 복수 구현체 선택, collection 주입, qualifier, primary, lazy, tag를 다루는 DI 심화 가이드입니다.

이 문서는 [DI & Pod](dependency-injection.md)를 읽은 뒤 보는 심화 가이드입니다. 기본 문서에서는 Pod 등록과 생성자 주입을 다루고, 여기서는 같은 타입의 구현체가 여러 개 있을 때 선택하거나 묶어서 주입하는 방법을 설명합니다.

## 복수 구현체 선택

같은 interface나 port를 구현하는 Pod가 여러 개 등록되면 단수 주입은 명시적인 선택 정책을 따릅니다. 우선순위는 `Qualifier`, 명시 name, `ApplicationContext.bind(PodBinding(...))`, `@Primary`, legacy parameter name fallback 순서입니다. 이 순서로도 하나를 고를 수 없으면 컨테이너는 임의의 후보를 선택하지 않고 `NoUniquePodError`를 발생시킵니다.

Application config에서 선택 정책을 관리하려면 binding을 등록합니다.

```python
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
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

간단한 경우에는 `context.bind_to_name(IEmailSender, "smtp")` 또는 `context.bind_to_type(IEmailSender, SmtpEmailSender)`를 사용할 수 있습니다. Binding은 Pod 등록 전에도 선언할 수 있으므로, 플러그인 자동 로딩 흐름을 유지하면서 application config만으로 단수 구현체 선택을 제어할 수 있습니다.

## Collection 주입

여러 구현체를 모두 사용해야 하면 단수 타입 대신 collection 타입을 선언합니다. Collection 주입은 단수 선택 정책을 적용하지 않고, 매칭되는 모든 후보를 Pod name 기준의 안정적인 순서로 주입합니다.

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

지원 타입은 `list[T]`, `tuple[T, ...]`, `dict[str, T]`입니다. Qualifier를 붙이면 collection에 들어갈 후보 전체를 필터링할 수 있습니다.

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

`contains(type_)`는 해당 타입 후보가 등록되어 있는지만 확인합니다. 후보가 둘 이상이라 단수 resolution이 모호해도 `contains(type_)`는 `True`일 수 있으며, 실제 단수 선택 가능성은 `get(type_)` 또는 생성자 주입 시점에 판정됩니다.

## @Qualifier

같은 인터페이스를 구현하는 Pod가 여러 개 있을 때, `Annotated` 타입 힌트에 `Qualifier`를 넣어 선택 조건을 지정합니다. `Qualifier`는 `Pod` 메타데이터를 받아 `bool`을 반환하는 selector를 인자로 받습니다.

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
    def __init__(
        self,
        repo: Annotated[
            IRepository,
            Qualifier(lambda p: p.type_ == MySQLRepository),
        ],
    ) -> None:
        self._repo = repo
```

여러 `Qualifier`를 중첩하면 AND 조건으로 동작합니다.

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

## @Primary

같은 타입이 여러 개일 때, `@Primary`가 붙은 Pod가 기본으로 선택됩니다.

```python
from spakky.core.pod.annotations.primary import Primary


@Pod()
@Primary()
class DefaultEmailSender:
    def send(self, to: str, body: str) -> None: ...
```

## @Lazy

처음 사용될 때까지 인스턴스 생성을 지연합니다.

```python
from spakky.core.pod.annotations.lazy import Lazy


@Pod()
@Lazy()
class HeavyService:
    def __init__(self) -> None:
        self.connection = create_expensive_connection()
```

## @Tag

`Tag`의 서브클래스를 정의하여 Pod에 메타데이터를 부여할 수 있습니다. 태그는 `ApplicationContext`의 태그 레지스트리에 자동 등록됩니다.

```python
from dataclasses import dataclass

from spakky.core.pod.annotations.pod import Pod
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
all_tags = app.application_context.tags

email_tags = app.application_context.list_tags(
    lambda t: isinstance(t, NotificationTag) and t.channel == "email"
)

exists = app.application_context.contains_tag(NotificationTag(channel="email"))
```
