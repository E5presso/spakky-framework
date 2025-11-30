from uuid import UUID

from fastapi import WebSocket
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from spakky.aspects.logging import Logging
from spakky.stereotype.usecase import UseCase

from spakky_fastapi.error import BadRequest
from spakky_fastapi.routes import (
    delete,
    get,
    head,
    options,
    patch,
    post,
    put,
    websocket,
)
from spakky_fastapi.stereotypes.api_controller import ApiController


class Dummy(BaseModel):
    name: str
    age: int


@ApiController("/dummy")
class DummyController:
    __name: str | None

    def __init__(self, name: str | None = None) -> None:
        self.__name = name

    async def just_function(self) -> str:
        return "Just Function!"

    @Logging()
    @get("", response_class=PlainTextResponse)
    async def get_dummy(self) -> str:
        return "Hello World!"

    @Logging()
    @get(
        "/file/{name}",
        response_class=FileResponse,
        description="Get file by given name",
    )
    async def get_file(self, name: str) -> str:
        return f"tests/apps/{name}"

    @Logging()
    @get(
        "/file-without-response-class/{name}",
        description="Get file by given name",
    )
    async def get_file_without_response_class(self, name: str) -> FileResponse:
        return FileResponse(f"tests/apps/{name}")

    @Logging()
    @post("")
    async def post_dummy(self, dummy: Dummy) -> Dummy:
        return dummy

    @Logging()
    @put("")
    async def put_dummy(self, dummy: Dummy) -> Dummy:
        return dummy

    @Logging()
    @patch("")
    async def patch_dummy(self, dummy: Dummy) -> Dummy:
        return dummy

    @Logging()
    @delete("/{id}")
    async def delete_dummy(self, id: UUID) -> UUID:
        return id

    @Logging()
    @head("", response_class=PlainTextResponse)
    async def head_dummy(self) -> None: ...

    @Logging()
    @options("", response_class=PlainTextResponse)
    async def options_dummy(self) -> str:
        return "Hello Options!"

    @Logging()
    @websocket("/ws")
    async def websocket_dummy(self, socket: WebSocket) -> None:
        await socket.accept()
        message: str = await socket.receive_text()
        await socket.send_text(message)
        await socket.close()

    @Logging()
    @get("/verify-email")
    async def verify_email(self, email: str) -> None:
        if "@" not in email:
            raise BadRequest("Invalid email")

    @Logging()
    @get("/error")
    async def raise_error(self) -> None:
        raise ValueError("Error!")


@UseCase()
class DummyUseCase:
    @get("/error", response_class=PlainTextResponse)
    async def raise_error(self) -> str:
        raise RuntimeError("Error!")
