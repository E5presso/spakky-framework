# Spakky FastAPI

FastAPI integration plugin for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-fastapi
```

Or install via Spakky extras:

```bash
pip install spakky[fastapi]
```

## Features

- **Automatic route registration**: Routes are registered from `@ApiController` classes
- **All HTTP methods**: GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS, WebSocket
- **OpenAPI integration**: Tags and documentation automatically configured
- **Error handling middleware**: Built-in exception handling with debug mode
- **Context management**: Request-scoped dependency injection support
- **Actuator endpoints**: Optional `/actuator/*` HTTP endpoints when `spakky-actuator` is loaded

## Usage

### Basic Controller

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

### Available Route Decorators

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

### Accessing FastAPI Instance

```python
from fastapi import FastAPI
from spakky.core.application.application import SpakkyApplication

# After application.start()
fast_api = application.container.get(FastAPI)
```

### Testing with TestClient

```python
from fastapi.testclient import TestClient

def test_get_user(application: SpakkyApplication) -> None:
    fast_api = application.container.get(FastAPI)
    client = TestClient(fast_api)
    response = client.get("/users/1")
    assert response.status_code == 200
```

## Distributed Tracing

`spakky-tracing`은 필수 의존성으로 자동 설치됩니다. `TracingMiddleware`가 자동으로 등록되어 모든 HTTP 요청에 대해 `TraceContext`를 전파합니다.

- 수신 요청의 `traceparent` 헤더에서 `TraceContext`를 추출하여 자식 스팬을 생성합니다
- 헤더가 없으면 새로운 루트 트레이스를 시작합니다
- 요청 완료 후 `TraceContext`를 자동으로 정리합니다

## Actuator Endpoints

`spakky-actuator` 플러그인을 함께 로드하면 FastAPI 앱에 표준 actuator route가 등록됩니다.

| Endpoint | Success | Unhealthy |
|----------|---------|-----------|
| `GET /actuator/health` | `200 OK` | `503 Service Unavailable` |
| `GET /actuator/readiness` | `200 OK` | `503 Service Unavailable` |
| `GET /actuator/liveness` | `200 OK` | `503 Service Unavailable` |
| `GET /actuator/info` | `200 OK` | N/A |

Endpoint exposure and base path are configured with `FastAPIActuatorConfig`.
Component detail exposure is controlled by `spakky.actuator.ActuatorConfig`.

```python
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.fastapi.actuator import FastAPIActuatorConfig

@Pod()
def fastapi_actuator_config() -> FastAPIActuatorConfig:
    return FastAPIActuatorConfig(
        base_path="/internal/actuator",
        readiness_enabled=False,
    )
```

## Components

| Component | Description |
|-----------|-------------|
| `ApiController` | Stereotype for REST API controllers with prefix and tags |
| `get`, `post`, `put`, etc. | Route decorators for HTTP methods |
| `websocket` | WebSocket endpoint decorator |
| `ErrorHandlingMiddleware` | Built-in exception handling middleware |
| `TracingMiddleware` | Trace context propagation middleware (`spakky-tracing` 필수 의존) |
| `FastAPIActuatorConfig` | FastAPI actuator endpoint exposure configuration |
| `RegisterActuatorPostProcessor` | Automatic actuator endpoint registration post-processor |
| `RegisterRoutesPostProcessor` | Automatic route registration post-processor |

## Configuration

The plugin automatically registers a `FastAPI` instance as a Pod. You can customize it by registering your own FastAPI instance before loading the plugin:

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

## License

MIT
