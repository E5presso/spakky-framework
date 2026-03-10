# 플러그인 API 가이드

이 문서는 Spakky Framework의 플러그인 시스템과 플러그인 개발 방법을 설명합니다.

---

## 개요

Spakky 플러그인 시스템은 Python의 `entry_points` 메커니즘을 사용하여 프레임워크 기능을 확장합니다. 플러그인은 다음과 같은 방식으로 동작합니다:

1. `pyproject.toml`에 `spakky.plugins` 그룹으로 entry point 등록
2. `SpakkyApplication.load_plugins()`가 등록된 플러그인 탐색
3. 각 플러그인의 `initialize(app: SpakkyApplication)` 함수 호출

---

## 플러그인 로딩

### 모든 플러그인 로드

```python
from spakky.core.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

app = SpakkyApplication(ApplicationContext())
app.load_plugins()  # 설치된 모든 spakky 플러그인 로드
app.scan()
app.start()
```

### 선택적 플러그인 로드

```python
from spakky.core.application.plugin import Plugin

# 특정 플러그인만 로드
app.load_plugins(include={
    Plugin(name="spakky-fastapi"),
    Plugin(name="spakky-sqlalchemy"),
})
```

---

## 공식 플러그인

### Core 플러그인 (자동 로드)

| 플러그인        | 설명                           |
| --------------- | ------------------------------ |
| `spakky-domain` | DDD 빌딩 블록                  |
| `spakky-data`   | Repository, Transaction 추상화 |
| `spakky-event`  | 인프로세스 이벤트 시스템       |

### UI 플러그인

| 플러그인         | 설명                       |
| ---------------- | -------------------------- |
| `spakky-fastapi` | FastAPI REST 컨트롤러 통합 |
| `spakky-typer`   | Typer CLI 컨트롤러 통합    |

### 인프라 플러그인

| 플러그인            | 설명                       |
| ------------------- | -------------------------- |
| `spakky-rabbitmq`   | RabbitMQ 이벤트 브로커     |
| `spakky-kafka`      | Apache Kafka 이벤트 브로커 |
| `spakky-sqlalchemy` | SQLAlchemy ORM 통합        |
| `spakky-security`   | 암호화/해싱/JWT 유틸리티   |
| `spakky-outbox`     | Transactional Outbox 패턴 |
| `spakky-outbox-sqlalchemy` | SQLAlchemy 기반 Outbox 저장소 |

---

## 플러그인 구조

플러그인 패키지의 표준 구조:

```
plugins/spakky-example/
├── pyproject.toml
├── README.md
├── CHANGELOG.md
└── src/
    └── spakky/
        └── plugins/
            └── example/
                ├── __init__.py
                ├── main.py              # initialize() 진입점
                ├── error.py             # 에러 클래스
                ├── post_processors/     # PostProcessor 구현
                └── ...
```

---

## 플러그인 개발

### 1. 패키지 구조 생성

```
plugins/spakky-myfeature/
├── pyproject.toml
├── README.md
└── src/
    └── spakky/
        └── plugins/
            └── myfeature/
                ├── __init__.py
                └── main.py
```

### 2. pyproject.toml 설정

```toml
[project]
name = "spakky-myfeature"
version = "0.1.0"
description = "My feature plugin for Spakky Framework"
dependencies = [
    "spakky",
]

# Entry point 등록 (필수!)
[project.entry-points."spakky.plugins"]
spakky-myfeature = "spakky.plugins.myfeature.main:initialize"

[tool.pyrefly]
module-name = "spakky.plugins.myfeature"
```

### 3. Plugin 식별자 정의

```python
# src/spakky/plugins/myfeature/__init__.py
from spakky.core.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-myfeature")
```

### 4. initialize 함수 구현

```python
# src/spakky/plugins/myfeature/main.py
from spakky.core.application.application import SpakkyApplication


def initialize(app: SpakkyApplication) -> None:
    """플러그인 초기화.

    SpakkyApplication.load_plugins()에 의해 자동 호출됩니다.

    Args:
        app: Spakky 애플리케이션 인스턴스
    """
    # Pod 등록
    app.add(MyFeatureService)
    app.add(MyFeaturePostProcessor)

    # 또는 패키지 스캔
    # app.scan(path="spakky.plugins.myfeature")
```

---

## 확장 포인트

플러그인은 다음 메커니즘으로 프레임워크를 확장합니다:

### PostProcessor

Pod 인스턴스 생성 후 추가 처리를 수행합니다.

```python
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.post_processor import IPostProcessor

@Pod()
class MyFeaturePostProcessor(IPostProcessor):
    """Pod 인스턴스에 기능 주입"""

    def post_process(self, pod: object) -> object:
        # Pod 인스턴스 수정 또는 래핑
        if hasattr(pod, "__myfeature__"):
            return MyFeatureWrapper(pod)
        return pod
```

### Aspect

횡단 관심사를 구현합니다.

```python
from spakky.core.aop.aspect import AsyncAspect
from spakky.core.aop.interfaces.aspect import IAsyncAspect
from spakky.core.aop.pointcut import Around

@AsyncAspect()
class MyFeatureAspect(IAsyncAspect):
    """커스텀 Aspect"""

    @Around(pointcut=lambda x: MyAnnotation.exists(x))
    async def around_async(self, joinpoint, *args, **kwargs):
        # 전처리
        result = await joinpoint(*args, **kwargs)
        # 후처리
        return result
```

### Stereotype

역할을 나타내는 특화된 Pod 데코레이터를 정의합니다.

```python
from dataclasses import dataclass
from spakky.core.pod.annotations.pod import Pod

@dataclass(eq=False)
class MyFeatureHandler(Pod):
    """MyFeature 핸들러 Stereotype"""
    ...
```

### Service

생명주기 관리가 필요한 백그라운드 서비스를 구현합니다.

```python
from spakky.core.pod.annotations.pod import Pod
from spakky.core.service.interfaces.service import IAsyncService
import asyncio

@Pod()
class MyFeatureBackgroundService(IAsyncService):
    """백그라운드에서 실행되는 서비스"""

    _stop_event: asyncio.Event

    def set_stop_event(self, stop_event: asyncio.Event) -> None:
        self._stop_event = stop_event

    async def start_async(self) -> None:
        """서비스 시작"""
        while not self._stop_event.is_set():
            await self.do_work()
            await asyncio.sleep(1)

    async def stop_async(self) -> None:
        """서비스 정지"""
        await self.cleanup()
```

---

## 플러그인 예시: FastAPI

FastAPI 플러그인이 어떻게 구현되어 있는지 살펴봅니다.

### Entry Point

```toml
# plugins/spakky-fastapi/pyproject.toml
[project.entry-points."spakky.plugins"]
spakky-fastapi = "spakky.plugins.fastapi.main:initialize"
```

### 초기화

```python
# plugins/spakky-fastapi/src/spakky/plugins/fastapi/main.py
def initialize(app: SpakkyApplication) -> None:
    """FastAPI 플러그인 초기화"""
    app.add(BindLifespanPostProcessor)
    app.add(AddBuiltInMiddlewaresPostProcessor)
    app.add(RegisterRoutesPostProcessor)
```

### PostProcessor 구현

```python
@Pod()
class RegisterRoutesPostProcessor(IPostProcessor):
    """Controller의 라우트를 FastAPI에 등록"""

    def __init__(self, fast_api: FastAPI) -> None:
        self.fast_api = fast_api

    def post_process(self, pod: object) -> object:
        if Controller.exists(type(pod)):
            self._register_routes(pod)
        return pod

    def _register_routes(self, controller: object) -> None:
        # 라우트 등록 로직
        ...
```

---

## 플러그인 의존성

플러그인 간 의존성은 `pyproject.toml`의 `dependencies`로 선언합니다:

```toml
[project]
name = "spakky-rabbitmq"
dependencies = [
    "spakky-event",  # spakky-event에 의존
    "aio-pika>=8.0.0",
]
```

코어 플러그인 의존 체인:

```
spakky → spakky-domain → spakky-data → spakky-event
```

---

## 테스트

플러그인 테스트 시 플러그인만 선택적으로 로드합니다:

```python
import pytest
from spakky.core.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
import spakky.plugins.myfeature

@pytest.fixture
def app():
    app = SpakkyApplication(ApplicationContext())
    app.load_plugins(include={spakky.plugins.myfeature.PLUGIN_NAME})
    app.scan(path="tests.apps")
    app.start()
    yield app
    app.stop()

def test_my_feature(app):
    service = app.container.get(MyFeatureService)
    assert service is not None
```

---

## 모범 사례

### 명시적 PLUGIN_NAME 정의

```python
# __init__.py
from spakky.core.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-myfeature")
```

### 에러 클래스 정의

```python
# error.py
from spakky.core.common.error import AbstractSpakkyFrameworkError

class MyFeatureError(AbstractSpakkyFrameworkError):
    """MyFeature 플러그인 기본 에러"""
    message = "MyFeature error occurred"
```

### 문서화

- `README.md` — 사용법, API 레퍼런스
- `CHANGELOG.md` — 버전별 변경 사항
- Docstring — 모든 공개 API에 작성

### 스캔보다 명시적 등록 선호

```python
# ✅ 권장: 명시적 등록
def initialize(app: SpakkyApplication) -> None:
    app.add(ServiceA)
    app.add(ServiceB)
    app.add(MyPostProcessor)

# ⚠️ 주의: 스캔은 예상치 못한 Pod 등록 가능
def initialize(app: SpakkyApplication) -> None:
    app.scan(path="spakky.plugins.myfeature")
```
