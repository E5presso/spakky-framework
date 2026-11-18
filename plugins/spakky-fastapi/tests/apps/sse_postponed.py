"""SSE controller whose annotations are strings until FastAPI resolves them."""

from __future__ import annotations

from collections.abc import AsyncIterator

from pydantic import BaseModel

from spakky.plugins.fastapi.routes import sse
from spakky.plugins.fastapi.routes.route import HTTPMethod
from spakky.plugins.fastapi.stereotypes.api_controller import ApiController


class Echo(BaseModel):
    text: str


@ApiController("/postponed")
class PostponedStreamController:
    @sse("/echo", methods=[HTTPMethod.POST])
    async def echo(self, body: Echo) -> AsyncIterator[Echo]:
        """Open a stream whose body and item annotations are strings."""

        async def events() -> AsyncIterator[Echo]:
            yield Echo(text=body.text)

        return events()
