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

## Usage

### Basic Controller

```python
from spakky_fastapi.stereotypes.api_controller import ApiController
from spakky_fastapi.routes import get, post

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
from spakky_fastapi.routes import (
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
from spakky.application.application import SpakkyApplication

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

## Components

| Component | Description |
|-----------|-------------|
| `ApiController` | Stereotype for REST API controllers with prefix and tags |
| `get`, `post`, `put`, etc. | Route decorators for HTTP methods |
| `websocket` | WebSocket endpoint decorator |
| `ErrorHandlingMiddleware` | Built-in exception handling middleware |
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
