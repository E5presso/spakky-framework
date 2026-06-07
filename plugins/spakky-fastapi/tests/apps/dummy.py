from uuid import UUID

from fastapi import Request, WebSocket
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from spakky.auth import (
    AuthRequirementDeniedError,
    ConflictingAuthMetadataError,
    protected,
    require_auth_context,
)
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.core.stereotype.usecase import UseCase
from typing import override

from spakky.plugins.fastapi.error import BadRequest
from spakky.plugins.fastapi.routes import (
    delete,
    get,
    head,
    options,
    patch,
    post,
    put,
    websocket,
)
from spakky.plugins.fastapi.stereotypes.api_controller import ApiController


class Dummy(BaseModel):
    name: str
    age: int


@ApiController("/dummy")
class DummyController(IApplicationContextAware):
    __name: str | None
    __application_context: IApplicationContext

    def __init__(self, name: str | None = None) -> None:
        self.__name = name

    @override
    def set_application_context(self, application_context: IApplicationContext) -> None:
        self.__application_context = application_context

    async def just_function(self) -> str:
        return "Just Function!"

    @get("", response_class=PlainTextResponse)
    async def get_dummy(self) -> str:
        return "Hello World!"

    @get(
        "/named",
        response_class=PlainTextResponse,
        name="Named Endpoint",
        description="Endpoint with explicit name",
    )
    async def get_named(self) -> str:
        """This docstring should be ignored since description is provided."""
        return "Named!"

    @get("/sync")
    def get_sync_dummy(self) -> dict[str, str]:
        return {"message": "sync ok"}

    @get(
        "/file/{name}",
        response_class=FileResponse,
        description="Get file by given name",
    )
    async def get_file(self, name: str) -> str:
        return f"tests/apps/{name}"

    @get(
        "/file-without-response-class/{name}",
        description="Get file by given name",
    )
    async def get_file_without_response_class(self, name: str) -> FileResponse:
        return FileResponse(f"tests/apps/{name}")

    @post("")
    async def post_dummy(self, dummy: Dummy) -> Dummy:
        return dummy

    @put("")
    async def put_dummy(self, dummy: Dummy) -> Dummy:
        return dummy

    @patch("")
    async def patch_dummy(self, dummy: Dummy) -> Dummy:
        return dummy

    @delete("/{id}")
    async def delete_dummy(self, id: UUID) -> UUID:
        return id

    @head("", response_class=PlainTextResponse)
    async def head_dummy(self) -> None: ...

    @options("", response_class=PlainTextResponse)
    async def options_dummy(self) -> str:
        return "Hello Options!"

    @websocket("/ws")
    async def websocket_dummy(self, socket: WebSocket) -> None:
        await socket.accept()
        message: str = await socket.receive_text()
        await socket.send_text(message)
        await socket.close()

    @protected
    @get("/auth/protected")
    async def protected_dummy(self) -> dict[str, str]:
        auth_context = require_auth_context(self.__application_context)
        return {"subject": auth_context.subject.id, "issuer": auth_context.issuer}

    @protected
    @get("/auth/denied")
    async def denied_dummy(self) -> None:
        raise AuthRequirementDeniedError()

    @protected
    @get("/auth/internal-error")
    async def auth_internal_error_dummy(self) -> None:
        raise ConflictingAuthMetadataError()

    @get("/request-path", response_class=PlainTextResponse)
    async def request_path_dummy(self, request: Request) -> str:
        return request.url.path

    @protected
    @websocket("/ws-protected")
    async def websocket_protected_dummy(self, socket: WebSocket) -> None:
        auth_context = require_auth_context(self.__application_context)
        await socket.accept()
        await socket.send_text(auth_context.subject.id)
        await socket.close()

    @get("/verify-email")
    async def verify_email(self, email: str) -> None:
        if "@" not in email:
            raise BadRequest("Invalid email")

    @get("/error")
    async def raise_error(self) -> None:
        raise ValueError("Error!")


@UseCase()
class DummyUseCase:
    @get("/error", response_class=PlainTextResponse)
    async def raise_error(self) -> str:
        raise RuntimeError("Error!")
