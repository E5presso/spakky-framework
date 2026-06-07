# Spakky FastAPI

[Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 FastAPI 통합 플러그인입니다.

## 설치

```bash
pip install spakky-fastapi
```

Spakky extras로도 설치할 수 있습니다.

```bash
pip install spakky[fastapi]
```

## 주요 기능

- **자동 route 등록**: `@ApiController` 클래스에서 route를 등록합니다.
- **모든 HTTP 메서드**: GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS, WebSocket
- **OpenAPI 통합**: tag와 documentation 자동 설정
- **에러 처리 middleware**: debug mode를 포함한 built-in exception handling
- **Context 관리**: request-scoped 의존성 주입 지원
- **Auth 경계 통합**: `spakky-auth` 보호 handler용 `AuthContext` seeding
- **Actuator endpoint**: `spakky-actuator` 로드 시 선택적 `/actuator/*` HTTP endpoint 제공

## 사용법

### 기본 Controller

```python
from spakky.plugins.fastapi.stereotypes.api_controller import ApiController
from spakky.plugins.fastapi.routes import get, post

@ApiController("/users", tags=["users"])
class UserController:
    def __init__(self, user_service: UserService) -> None:
        self.user_service = user_service

    @get("/{user_id}")
    async def get_user(self, user_id: int) -> User:
        return await self.user_service.get(user_id)

    @post("")
    async def create_user(self, request: CreateUserRequest) -> User:
        return await self.user_service.create(request)
```

### 사용 가능한 route decorator

```python
from spakky.plugins.fastapi.routes import (
    get,
    post,
    put,
    delete,
    patch,
    head,
    options,
    websocket,
)

@ApiController("/api")
class MyController:
    @get("/items")
    async def list_items(self) -> list[Item]:
        ...

    @post("/items")
    async def create_item(self, item: CreateItemRequest) -> Item:
        ...

    @put("/items/{item_id}")
    async def update_item(self, item_id: int, item: UpdateItemRequest) -> Item:
        ...

    @delete("/items/{item_id}")
    async def delete_item(self, item_id: int) -> None:
        ...

    @websocket("/ws")
    async def websocket_endpoint(self, websocket: WebSocket) -> None:
        await websocket.accept()
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Echo: {data}")
```

### FastAPI 인스턴스 접근

```python
from fastapi import FastAPI
from spakky.core.application.application import SpakkyApplication

# application.start() 이후
fast_api = application.container.get(FastAPI)
```

### TestClient 테스트

```python
from fastapi.testclient import TestClient

def test_get_user(application: SpakkyApplication) -> None:
    fast_api = application.container.get(FastAPI)
    client = TestClient(fast_api)
    response = client.get("/users/1")
    assert response.status_code == 200
```

## 분산 트레이싱

`spakky-tracing`은 필수 의존성으로 자동 설치됩니다. `TracingMiddleware`가 자동으로 등록되어 모든 HTTP 요청에 대해 `TraceContext`를 전파합니다.

- 수신 요청의 `traceparent` 헤더에서 `TraceContext`를 추출하여 자식 스팬을 생성합니다
- 헤더가 없으면 새로운 루트 트레이스를 시작합니다
- 요청 완료 후 `TraceContext`를 자동으로 정리합니다

## Actuator endpoint

`spakky-actuator` 플러그인을 함께 로드하면 FastAPI 앱에 표준 actuator route가 등록됩니다.
HTTP payload는 transport-neutral core result shape를 그대로 반영합니다.

| Endpoint | 정상 | 비정상 |
|----------|---------|-----------|
| `GET /actuator/health` | `200 OK` | `503 Service Unavailable` |
| `GET /actuator/readiness` | `200 OK` | `503 Service Unavailable` |
| `GET /actuator/liveness` | `200 OK` | `503 Service Unavailable` |
| `GET /actuator/info` | `200 OK` | N/A |

FastAPI actuator routes are unauthenticated by default. In production, expose
them only behind internal networking, an API gateway, a reverse-proxy allowlist,
or another explicit access-control layer. Disable unneeded endpoints and set
`ActuatorConfig(include_details=False)` before allowing actuator traffic outside
a trusted boundary.

Endpoint 노출과 base path는 `FastAPIActuatorConfig`로 설정합니다.
Component detail 노출은 `spakky.actuator.ActuatorConfig`로 제어합니다.
`readiness`는 traffic/work readiness용이며, `liveness`는 process-local check로 남아 외부 의존성 실패와 독립적이어야 합니다.

```python
from spakky.core.pod.annotations.pod import Pod
from spakky.actuator import ActuatorConfig
from spakky.plugins.fastapi.actuator import FastAPIActuatorConfig


@Pod()
def actuator_config() -> ActuatorConfig:
    return ActuatorConfig(include_details=False)


@Pod()
def fastapi_actuator_config() -> FastAPIActuatorConfig:
    return FastAPIActuatorConfig(
        base_path="/internal/actuator",
        readiness_enabled=False,
    )
```

FastAPI adapter는 플러그인별 상세 check를 자동 등록하지 않습니다.
데이터베이스, broker, worker readiness가 actuator 출력에 영향을 줘야 한다면 애플리케이션에 `spakky.actuator.AbstractHealthProbe` Pod를 등록하세요.

## Auth 경계 통합

`spakky-fastapi`는 HTTP/WebSocket 경계에서 `spakky-auth`의 `AuthContext`를 seed합니다.
FastAPI wrapper가 Spakky request context를 clear한 뒤 credential 전달체를 추출하고,
사용자 handler 호출 전에 인증 provider로 `AuthContext`를 저장합니다. 보호된 handler는
인증만을 위해 FastAPI `Request`, `WebSocket`, 또는 `AuthContext` 파라미터를 선언할 필요가 없습니다.

- HTTP는 `Authorization: Bearer <token>`을 지원합니다.
- WebSocket은 `Authorization: Bearer <token>`과 `access_token=<token>` connection query를 지원합니다.
- HTTP auth failure는 CHALLENGE 401, DENY 403, ERROR 500으로 매핑됩니다.
- WebSocket auth failure는 보호된 handler 호출 전에 connection close로 처리됩니다.

## 구성 요소

| 컴포넌트 | 설명 |
|-----------|-------------|
| `ApiController` | prefix와 tag를 가진 REST API controller용 stereotype |
| `get`, `post`, `put`, etc. | HTTP method용 route decorator |
| `websocket` | WebSocket endpoint decorator |
| `ErrorHandlingMiddleware` | built-in exception handling middleware |
| `TracingMiddleware` | trace context propagation middleware (`spakky-tracing` 필수 의존) |
| `FastAPIActuatorConfig` | FastAPI actuator endpoint 노출 설정 |
| `RegisterActuatorPostProcessor` | 자동 actuator endpoint 등록 post-processor |
| `RegisterRoutesPostProcessor` | 자동 route 등록 post-processor |

## 설정

플러그인은 `FastAPI` 인스턴스를 Pod로 자동 등록합니다. 플러그인을 로드하기 전에 직접 만든 FastAPI 인스턴스를 등록하면 커스터마이즈할 수 있습니다:

```python
from fastapi import FastAPI

@Pod()
def custom_fastapi() -> FastAPI:
    return FastAPI(
        title="My API",
        description="Custom API configuration",
        version="1.0.0",
    )
```

## 라이선스

MIT
