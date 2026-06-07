# DI & Pod

> `@Pod`, 생성자 주입, qualifier, plugin loading을 처음부터 따라가는 Spakky 기본 가이드입니다.

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

## 다음 단계

같은 interface의 구현체가 여러 개 있거나, `@Qualifier`, `@Primary`, collection 주입, `@Lazy`, `@Tag`가 필요해지면 [DI & Pod 심화](dependency-injection-advanced.md)를 이어서 보세요.

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
