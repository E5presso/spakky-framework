# FastAPI 통합

`spakky-fastapi`는 FastAPI 엔드포인트를 `@ApiController` 클래스로 구조화합니다.

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

## 분산 트레이싱 (Optional)

`spakky-tracing`이 설치되면 `TracingMiddleware`가 자동으로 등록되어 모든 HTTP 요청에 대해 W3C `TraceContext`를 전파합니다.

```bash
pip install spakky-fastapi[tracing]
```

`AddBuiltInMiddlewaresPostProcessor`가 컨테이너에 `ITracePropagator`가 존재하는지 확인하고, 있으면 `TracingMiddleware`를 FastAPI에 자동 추가합니다.

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
