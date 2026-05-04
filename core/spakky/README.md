# Spakky

[Spakky Framework](https://github.com/E5presso/spakky-framework)의 코어 모듈입니다. Python을 위한 Spring-inspired 의존성 주입 프레임워크를 제공합니다.

## 설치

```bash
pip install spakky
```

플러그인을 함께 설치할 수도 있습니다.

```bash
pip install spakky[fastapi]
pip install spakky[fastapi,kafka,security]
```

## 주요 기능

- **의존성 주입**: 생성자 주입 기반의 강력한 IoC 컨테이너
- **관점 지향 프로그래밍**: `@Aspect`로 횡단 관심사를 처리합니다.
- **플러그인 시스템**: entry point 기반 확장 아키텍처
- **스테레오타입**: 의미를 드러내는 어노테이션 (`@Controller`, `@UseCase`, etc.)
- **스코프**: Singleton, Prototype, Context scope bean
- **타입 안전성**: Python 타입 힌트 기반 설계
- **비동기 우선**: async/await 네이티브 지원

## 빠른 시작

### Pod 정의

```python
from spakky.core.pod.annotations.pod import Pod

@Pod()
class UserRepository:
    def find_by_id(self, user_id: int) -> User | None:
        # Database query logic
        pass

@Pod()
class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    def get_user(self, user_id: int) -> User | None:
        return self.repository.find_by_id(user_id)
```

### 애플리케이션 부트스트랩

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
import my_app

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()
    .scan(my_app)  # 또는 .scan()으로 호출자 패키지 자동 감지
    .start()
)

# 컨테이너에서 서비스 조회
user_service = app.container.get(UserService)
```

> **📘 자동 스캔**: `scan()`을 인자 없이 호출하면 호출자의 패키지를 자동 감지해 스캔합니다. 애플리케이션 루트가 `sys.path`에 없을 수 있는 Docker 환경에서도 프레임워크가 필요한 경로를 자동으로 추가합니다.

### Discovery Manifest

Scan discovery manifest 재사용은 선택 기능이며 컨테이너 캐시를 대체하지 않습니다.
`scan()` 전에 활성화하면 발견된 Pod/Tag 후보를 저장하고, scan 대상, exclude pattern, Python 버전, schema 버전, source file mtime/size가 그대로일 때 재사용합니다.

```python
from pathlib import Path

from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

app = (
    SpakkyApplication(ApplicationContext())
    .enable_startup_diagnostics()
    .enable_discovery_manifest(Path(".spakky/cache/discovery-manifest.json"))
    .scan(my_app)
)

scan_record = app.startup_report.records[0]
decision = scan_record.diagnostic_details[0].value  # miss, hit, stale_schema, stale_input
```

경로를 지정하지 않으면 Spakky는 결정적인 project-local cache path인 `.spakky/cache/discovery-manifest.json`을 사용합니다. manifest가 없거나 오래되었거나 형식이 잘못되면 새 discovery로 fallback하고 그 결정을 startup diagnostics에 기록합니다. decision 값은 `miss`, `hit`, `stale_schema`, `stale_input`입니다. `hit`은 저장된 후보를 일반 등록 경로로 재생하고, 나머지 decision은 새 discovery를 수행합니다.

### 시작 진단

Startup diagnostics는 opt-in 기능입니다. 기본 recorder는 no-op이므로 명시적으로 diagnostics를 활성화하기 전까지 기존 startup 동작은 바뀌지 않습니다.

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

app = SpakkyApplication(ApplicationContext()).enable_startup_diagnostics()

app.startup_phase_recorder.record_success(
    phase_name="scan",
    elapsed_seconds=0.12,
    processed_count=4,
)

with app.startup_phase_recorder.record_phase(phase_name="start") as phase:
    phase.set_processed_count(1)
    app.start()

report = app.startup_report
first_phase = report.records[0]
```

`StartupReport`는 각 startup phase 이름, 경과 시간(초), 처리 count, 성공/실패 상태, 선택적 diagnostic detail, 선택적 구조화 failure summary를 저장합니다. Failure summary는 원본 exception 객체를 보관하지 않고 exception type name, message, diagnostic detail만 유지합니다. 애플리케이션 startup pipeline은 실행 순서대로 phase를 기록합니다.
`load_plugins`, `scan`, `registration`, `post_processor_registration`,
`instantiation`, `post_processing`, and `service_start`.

DI dependency 실패는 기존 exception type을 유지하면서 `Pod.dependencies`에서 얻은 구조화된 dependency diagnostics를 붙입니다. 실패한 Pod, 의존성 파라미터, 요청 타입, 의존성 경로를 함께 보여줍니다.

## Pod 스코프

```python
from spakky.core.pod.annotations.pod import Pod

# Singleton(기본값): 컨테이너당 인스턴스 하나
@Pod(scope=Pod.Scope.SINGLETON)
class SingletonService:
    pass

# Prototype: 요청마다 새 인스턴스
@Pod(scope=Pod.Scope.PROTOTYPE)
class PrototypeService:
    pass

# Context: request/context lifecycle에 묶인 인스턴스
@Pod(scope=Pod.Scope.CONTEXT)
class ContextScopedService:
    pass
```

## Qualifier, Primary, Binding

```python
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.annotations.primary import Primary
from spakky.core.pod.binding import PodBinding

# 이름 기반 qualifier
@Pod(name="mysql")
class MySQLRepository(IRepository):
    pass

@Pod(name="postgres")
class PostgresRepository(IRepository):
    pass

# Primary: 구현체가 여러 개일 때 우선 선택
@Primary()
@Pod()
class DefaultRepository(IRepository):
    pass

# application config 기반 binding: Primary보다 우선
context = ApplicationContext()
context.bind(PodBinding(interface=IRepository, implementation_name="postgres"))
context.add(MySQLRepository)
context.add(PostgresRepository)
context.add(DefaultRepository)

repository = context.get(IRepository)  # PostgresRepository
```

## Stereotype

```python
from spakky.core.stereotype.controller import Controller
from spakky.core.stereotype.usecase import UseCase

@Controller()
class UserController:
    """관련 handler를 묶습니다."""
    pass

@UseCase()
class CreateUserUseCase:
    """비즈니스 로직을 캡슐화합니다."""
    pass
```

## 관점 지향 프로그래밍

```python
from dataclasses import dataclass
from spakky.core.aop.aspect import Aspect
from spakky.core.aop.interfaces.aspect import IAspect
from spakky.core.aop.pointcut import Before, After
from spakky.core.common.annotation import FunctionAnnotation
from spakky.core.pod.annotations.order import Order

@dataclass
class Traced(FunctionAnnotation): ...

# custom aspect 생성
@Order(0)
@Aspect()
class TracingAspect(IAspect):
    @Before(lambda m: Traced.exists(m))
    def before(self, *args, **kwargs) -> None:
        print("Before method execution")

    @After(lambda m: Traced.exists(m))
    def after(self, *args, **kwargs) -> None:
        print("After method execution")

# 메서드에 적용
@Pod()
class MyService:
    @Traced()
    def my_method(self) -> str:
        return "Hello"
```

### 비동기 Aspect

```python
from spakky.core.aop.aspect import AsyncAspect
from spakky.core.aop.interfaces.aspect import IAsyncAspect
from spakky.core.aop.pointcut import Around

@Order(0)
@AsyncAspect()
class TimingAspect(IAsyncAspect):
    @Around(lambda m: hasattr(m, "__timed__"))
    async def around_async(self, joinpoint, *args, **kwargs):
        start = time.time()
        result = await joinpoint(*args, **kwargs)
        elapsed = time.time() - start
        print(f"Execution time: {elapsed:.2f}s")
        return result
```

## Context 관리

ApplicationContext는 context-scoped value storage를 제공합니다.

```python
from spakky.core.application.application_context import ApplicationContext

context = ApplicationContext()

# 고유 context ID 조회
context_id = context.get_context_id()

# context value 저장 및 조회
context.set_context_value("user_id", 123)
user_id = context.get_context_value("user_id")  # Returns 123

# context 정리(system-managed key 제외)
context.clear_context()
```

> **⚠️ 참고**: `"__spakky_context_id__"` 같은 system-managed key는 `set_context_value()`로 덮어쓸 수 없습니다.

## Tag Registry

ApplicationContext는 커스텀 metadata tag 관리를 위해 `ITagRegistry`를 구현합니다. Tag는 런타임에 등록하고 조회할 수 있는 dataclass 기반 어노테이션입니다.

### 커스텀 Tag 정의

```python
from dataclasses import dataclass
from spakky.core.pod.annotations.tag import Tag

@dataclass(eq=False)
class MyCustomTag(Tag):
    """특정 component를 표시하는 custom tag입니다."""
    category: str = ""
```

### Tag 등록과 조회

```python
from spakky.core.application.application_context import ApplicationContext

context = ApplicationContext()

# tag 등록
tag = MyCustomTag(category="database")
context.register_tag(tag)

# tag 존재 여부 확인
exists = context.contains_tag(tag)  # True

# 모든 tag 조회
all_tags = context.tags  # frozenset of all registered tags

# selector로 tag 필터링
db_tags = context.list_tags(lambda t: isinstance(t, MyCustomTag) and t.category == "database")
```

### Tag Registry 인식 Pod

Pod는 `ITagRegistryAware`를 통해 tag registry를 받을 수 있습니다.

```python
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.aware.tag_registry_aware import ITagRegistryAware
from spakky.core.pod.interfaces.tag_registry import ITagRegistry

@Pod()
class SchemaRegistry(ITagRegistryAware):
    def __init__(self) -> None:
        self._tag_registry: ITagRegistry | None = None

    def set_tag_registry(self, tag_registry: ITagRegistry) -> None:
        self._tag_registry = tag_registry
        # 등록된 tag 접근
        for tag in tag_registry.list_tags(MyCustomTag.exists):
            # tag 처리...
            pass
```

## 플러그인 시스템

플러그인은 entry point를 통해 프레임워크 기능을 확장합니다.

### 플러그인 생성

1. `plugins/` 디렉토리에서 `uv init --lib spakky-<name>`으로 패키지를 생성합니다.
2. 루트 `pyproject.toml`의 `[tool.uv.workspace]` members에 등록합니다.
3. 플러그인의 `pyproject.toml`에 entry point를 정의합니다.

```toml
[project.entry-points."spakky.plugins"]
spakky-<name> = "spakky.plugins.<name>.main:initialize"
```

4. 초기화 함수를 구현합니다.

```python
# spakky.plugins.<name>/main.py 내부
from spakky.core.application.application import SpakkyApplication

def initialize(app: SpakkyApplication) -> None:
    # plugin component 등록
    pass
```

자세한 내용은 [기여 가이드](../../CONTRIBUTING.md#-plugin-development)를 참고하세요.

## 사용 가능한 플러그인

| 플러그인 | 설명 |
|--------|-------------|
| [`spakky-fastapi`](https://pypi.org/project/spakky-fastapi/) | FastAPI 통합 |
| [`spakky-typer`](https://pypi.org/project/spakky-typer/) | Typer CLI 통합 |
| [`spakky-sqlalchemy`](https://pypi.org/project/spakky-sqlalchemy/) | SQLAlchemy ORM 통합 |
| [`spakky-kafka`](https://pypi.org/project/spakky-kafka/) | Apache Kafka event system |
| [`spakky-rabbitmq`](https://pypi.org/project/spakky-rabbitmq/) | RabbitMQ event system |
| [`spakky-celery`](https://pypi.org/project/spakky-celery/) | Celery task dispatch |
| [`spakky-logging`](https://pypi.org/project/spakky-logging/) | AOP 기반 구조화 로깅 |
| [`spakky-opentelemetry`](https://pypi.org/project/spakky-opentelemetry/) | OpenTelemetry SDK bridge |
| [`spakky-security`](https://pypi.org/project/spakky-security/) | 보안 유틸리티 |

## 코어 모듈

| 모듈 | 설명 |
|--------|-------------|
| `spakky.core.pod` | 의존성 주입 컨테이너와 어노테이션 |
| `spakky.core.aop` | 관점 지향 프로그래밍 프레임워크 |
| `spakky.core.application` | 애플리케이션 컨텍스트와 생명주기 |
| `spakky.core.stereotype` | 의미 기반 stereotype 어노테이션 |
| `spakky.core.service` | 서비스 생명주기 인터페이스 |
| `spakky.core.common` | 코어 유틸리티(annotation, types, metadata) |
| `spakky.core.utils` | 유틸리티 함수 |

## 관련 패키지

| 패키지 | 설명 |
|---------|-------------|
| [`spakky-domain`](https://pypi.org/project/spakky-domain/) | DDD 빌딩 블록(Entity, AggregateRoot, ValueObject, Event) |
| [`spakky-data`](https://pypi.org/project/spakky-data/) | Repository와 transaction 추상화 |
| [`spakky-event`](https://pypi.org/project/spakky-event/) | Event handling(`@EventHandler` stereotype) |
| [`spakky-task`](https://pypi.org/project/spakky-task/) | Task queue 추상화(`@TaskHandler`, `@task`, `@schedule`) |
| [`spakky-tracing`](https://pypi.org/project/spakky-tracing/) | 분산 트레이싱 추상화(TraceContext, Propagator) |
| [`spakky-outbox`](https://pypi.org/project/spakky-outbox/) | Transactional Outbox 패턴(OutboxEventBus, Relay) |

## 라이선스

MIT
