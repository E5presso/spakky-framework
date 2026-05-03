# FastAPI 통합

> `spakky-fastapi`는 FastAPI 엔드포인트를 `@ApiController` 클래스로 구조화합니다.
> Controller Pod를 스캔하면 route decorator가 붙은 메서드를 FastAPI 라우터에 자동 등록합니다.

---

## 기본 설정

```python
from fastapi import FastAPI
from spakky.core.pod.annotations.pod import Pod
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
import apps

@Pod(name="api")
def get_api() -> FastAPI:
    return FastAPI(debug=True)

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()
    .scan(apps)
    .add(get_api)
    .start()
)

api: FastAPI = app.container.get(type_=FastAPI)
```

`app.start()` 시점에 `RegisterRoutesPostProcessor`가 `@ApiController` Pod를 찾아 `FastAPI.include_router()`로 라우트를 등록합니다. FastAPI 서버는 Spakky가 직접 실행하지 않으므로, ASGI 서버가 import할 수 있는 모듈 전역에 `api` 객체를 노출합니다.

```python
# main.py
from fastapi import FastAPI
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod

import apps
import spakky.plugins.fastapi


@Pod()
def get_api() -> FastAPI:
    return FastAPI(title="Orders API")


spakky_app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(include={spakky.plugins.fastapi.PLUGIN_NAME})
    .scan(apps)
    .add(get_api)
    .start()
)

api: FastAPI = spakky_app.container.get(FastAPI)
```

```bash
uvicorn main:api --reload
```

FastAPI lifespan은 `BindLifespanPostProcessor`가 감싸므로, ASGI 서버가 종료될 때 `ApplicationContext.stop()`이 호출되어 `IService`/`IAsyncService` 리소스가 정리됩니다.

---

## @ApiController

### HTTP 메서드 데코레이터

```python
from pydantic import BaseModel
from fastapi import WebSocket
from fastapi.responses import PlainTextResponse
from spakky.plugins.fastapi.routes import (
    get, post, put, patch, delete, head, options, websocket,
)
from spakky.plugins.fastapi.stereotypes.api_controller import ApiController

class UserRequest(BaseModel):
    name: str
    email: str

class UserResponse(BaseModel):
    id: str
    name: str
    email: str

@ApiController("/users")
class UserController:
    _service: UserService

    def __init__(self, service: UserService) -> None:
        self._service = service

    @get("", response_class=PlainTextResponse)
    async def list_users(self) -> str:
        """GET /users"""
        return "User list"

    @get("/{user_id}")
    async def get_user(self, user_id: str) -> UserResponse:
        """GET /users/{user_id}"""
        user = self._service.get_user(user_id)
        return UserResponse(id=user_id, name=user.name, email=user.email)

    @post("")
    async def create_user(self, request: UserRequest) -> UserResponse:
        """POST /users"""
        user = self._service.create(request.name, request.email)
        return UserResponse(id=str(user.uid), name=user.name, email=user.email)

    @put("/{user_id}")
    async def update_user(self, user_id: str, request: UserRequest) -> UserResponse:
        """PUT /users/{user_id}"""
        user = self._service.update(user_id, request.name, request.email)
        return UserResponse(id=user_id, name=user.name, email=user.email)

    @patch("/{user_id}")
    async def patch_user(self, user_id: str, request: UserRequest) -> UserResponse:
        """PATCH /users/{user_id}"""
        return UserResponse(id=user_id, name=request.name, email=request.email)

    @delete("/{user_id}")
    async def delete_user(self, user_id: str) -> dict:
        """DELETE /users/{user_id}"""
        self._service.delete(user_id)
        return {"deleted": user_id}

    @head("")
    async def head_users(self) -> None:
        """HEAD /users"""
        ...

    @options("")
    async def options_users(self) -> str:
        """OPTIONS /users"""
        return "GET, POST, PUT, PATCH, DELETE"
```

### UseCase와 에러 매핑

Controller에는 Repository를 직접 주입하지 말고 `@UseCase()` Pod를 주입합니다. 예상 가능한 HTTP 실패는 `spakky.plugins.fastapi.error`의 에러 클래스로 변환하면 `ErrorHandlingMiddleware`가 JSON 응답으로 바꿉니다.

```python
from pydantic import BaseModel

from spakky.plugins.fastapi.error import Conflict, NotFound
from spakky.plugins.fastapi.routes import get, post
from spakky.plugins.fastapi.stereotypes.api_controller import ApiController


class CreateOrderRequest(BaseModel):
    customer_id: str
    total_amount: float


class OrderResponse(BaseModel):
    order_id: str
    status: str


@ApiController("/orders")
class OrderController:
    def __init__(
        self,
        create_order: CreateOrderUseCase,
        get_order: GetOrderUseCase,
    ) -> None:
        self._create_order = create_order
        self._get_order = get_order

    @post("", status_code=201)
    async def create_order(self, request: CreateOrderRequest) -> OrderResponse:
        result = await self._create_order.execute(
            request.customer_id,
            request.total_amount,
        )
        if result.conflicted:
            raise Conflict()
        return OrderResponse(order_id=str(result.order_id), status=result.status)

    @get("/{order_id}")
    async def get_order(self, order_id: str) -> OrderResponse:
        order = await self._get_order.execute(order_id)
        if order is None:
            raise NotFound()
        return OrderResponse(order_id=str(order.uid), status=order.status.value)
```

`@post(..., status_code=201)`처럼 route decorator에 전달한 옵션은 내부 `Route` annotation에 저장되고 그대로 `FastAPI.add_api_route()`에 전달됩니다. 반환 타입이 Pydantic 모델이면 `RegisterRoutesPostProcessor`가 `response_model`을 자동 추론합니다.

### WebSocket

```python
@ApiController("/chat")
class ChatController:
    @websocket("/ws")
    async def chat(self, socket: WebSocket) -> None:
        """WebSocket /chat/ws"""
        await socket.accept()
        while True:
            message = await socket.receive_text()
            await socket.send_text(f"Echo: {message}")
```

---

## 분산 트레이싱

`spakky-tracing`은 `spakky-fastapi`의 필수 의존성입니다. 컨테이너에 `ITracePropagator`가 등록되어 있으면 `TracingMiddleware`가 자동으로 등록되어 모든 HTTP 요청에 대해 W3C `TraceContext`를 전파합니다.

`AddBuiltInMiddlewaresPostProcessor`가 컨테이너에서 `get_or_none(ITracePropagator)`로 propagator를 조회하고, 있으면 `TracingMiddleware`를 FastAPI에 자동 추가합니다.

- 수신 요청의 `traceparent` 헤더에서 `TraceContext`를 추출하여 자식 스팬을 생성합니다
- 헤더가 없으면 새로운 루트 트레이스를 시작합니다
- 응답 헤더에 `traceparent`를 자동 주입합니다
- 요청 완료 후 `TraceContext`를 자동으로 정리합니다

별도 설정이나 코드 변경 없이, 플러그인 로드만으로 동작합니다.

---

## 라우트 옵션

FastAPI의 라우트 옵션을 데코레이터에 전달할 수 있습니다.

```python
from fastapi.responses import FileResponse

@ApiController("/files")
class FileController:
    @get(
        "/{filename}",
        response_class=FileResponse,
        name="Download File",
        description="파일 다운로드 엔드포인트",
    )
    async def download(self, filename: str) -> str:
        return f"storage/{filename}"
```
