from collections.abc import AsyncIterator, Iterator
from itertools import chain
from typing import Any, override

import anyio
from fastapi import Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel
from spakky.auth import protected, require_auth_context
from spakky.core.aop.aspect import Aspect
from spakky.core.aop.interfaces.aspect import IAspect
from spakky.core.aop.pointcut import Around
from spakky.core.common.annotation import FunctionAnnotation
from spakky.core.common.types import Func
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)

from spakky.plugins.fastapi.routes import get, sse
from spakky.plugins.fastapi.routes.route import HTTPMethod
from spakky.plugins.fastapi.stereotypes.api_controller import ApiController


class Tick(BaseModel):
    number: int


class Countdown(BaseModel):
    start: int


@Pod()
class StreamJournal:
    """Records what stream endpoints did so tests can observe side effects."""

    entries: list[str]

    def __init__(self) -> None:
        self.entries = []


class Audited(FunctionAnnotation):
    """Marks a stream method whose events are preceded by an audit event."""


@Aspect()
class AuditAspect(IAspect):
    """Sync aspect proving AOP still applies to SSE controller methods."""

    @Around(Audited.exists)
    @override
    def around(
        self,
        joinpoint: Func,
        *args: Any,  # Any: IAspect contract
        **kwargs: Any,  # Any: IAspect contract
    ) -> Any:  # Any: IAspect contract
        return chain([{"audited-by": "aspect"}], joinpoint(*args, **kwargs))


@ApiController("/stream")
class StreamController(IApplicationContextAware):
    __journal: StreamJournal
    __application_context: IApplicationContext

    def __init__(self, journal: StreamJournal) -> None:
        self.__journal = journal

    @override
    def set_application_context(self, application_context: IApplicationContext) -> None:
        self.__application_context = application_context

    @sse("/events")
    async def events(self) -> AsyncIterator[ServerSentEvent]:
        """Stream explicit server-sent events."""
        yield ServerSentEvent(data={"step": 1}, event="progress", id="1")
        yield ServerSentEvent(raw_data="done", event="finished", id="2", retry=3000)
        yield ServerSentEvent(comment="bye")

    @sse("/ticks/{count}")
    async def ticks(self, count: int, start: int = 0) -> AsyncIterator[Tick]:
        for number in range(start, start + count):
            yield Tick(number=number)

    @sse("/sync")
    def sync_ticks(self) -> Iterator[Tick]:
        yield Tick(number=1)
        yield Tick(number=2)

    @sse("/countdown", methods=[HTTPMethod.POST], name="Start Countdown")
    async def countdown(self, body: Countdown) -> AsyncIterator[dict[str, int]]:
        for remaining in range(body.start, 0, -1):
            yield {"remaining": remaining}

    @sse("/request-path")
    async def request_path(self, request: Request) -> AsyncIterator[dict[str, str]]:
        yield {"path": request.url.path}

    @protected
    @sse("/me")
    async def me(self) -> AsyncIterator[dict[str, str]]:
        auth_context = require_auth_context(self.__application_context)
        yield {"subject": auth_context.subject.id}

    @Audited()
    @sse("/audited")
    def audited(self) -> Iterator[dict[str, str]]:
        yield {"audited": "yes"}

    @sse("/endless")
    async def endless(self) -> AsyncIterator[dict[str, str]]:
        try:
            yield {"state": "started"}
            await anyio.sleep_forever()
        finally:
            self.__journal.entries.append("endless-closed")

    @get("/native", response_class=EventSourceResponse)
    async def native(self) -> AsyncIterator[Tick]:
        yield Tick(number=7)

    @get("/declared", response_model=Tick, response_class=EventSourceResponse)
    async def declared(self) -> AsyncIterator[Tick]:
        yield Tick(number=9)
