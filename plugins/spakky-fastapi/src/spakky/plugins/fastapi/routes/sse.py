"""Server-Sent Events route decorator for FastAPI controllers.

Provides the @sse decorator for marking controller generator methods as
`text/event-stream` endpoints backed by FastAPI's native `fastapi.sse` support.
"""

from collections.abc import Callable, Sequence
from inspect import isasyncgenfunction, isgeneratorfunction
from typing import Any

from fastapi import params
from fastapi.sse import EventSourceResponse
from spakky.plugins.fastapi.error import AbstractSpakkyFastAPIError
from spakky.plugins.fastapi.routes.route import HTTPMethod, Route


class SseEndpointNotGeneratorError(AbstractSpakkyFastAPIError):
    """Raised when @sse decorates a method that is not a generator function."""

    message = "The @sse decorator can only be used on generator methods."


def sse[T](
    path: str,
    methods: set[HTTPMethod] | list[HTTPMethod] | None = None,
    status_code: int | None = None,
    tags: list[str] | None = None,
    dependencies: Sequence[params.Depends] | None = None,
    summary: str | None = None,
    description: str | None = None,
    response_description: str = "Successful Response",
    responses: dict[int | str, dict[str, Any]] | None = None,
    deprecated: bool | None = None,
    operation_id: str | None = None,
    include_in_schema: bool = True,
    name: str | None = None,
    openapi_extra: dict[str, Any] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to mark a controller generator method as an SSE stream.

    The decorated method must be an async generator (or a sync generator, which
    FastAPI iterates in its thread pool). Each yielded `ServerSentEvent` is
    written with its `event`/`id`/`retry`/`comment` fields; any other yielded
    value is JSON-encoded into the `data:` field. Keep-alive comments and
    cancellation on client disconnect are handled by FastAPI.

    Args:
        path: The URL path for this route.
        methods: HTTP methods this stream handles. None means GET only.
        status_code: HTTP status code for successful responses.
        tags: OpenAPI tags for grouping endpoints.
        dependencies: FastAPI dependencies to inject.
        summary: Short summary for OpenAPI documentation.
        description: Detailed description for OpenAPI documentation.
        response_description: Description of successful response.
        responses: Additional response schemas for OpenAPI.
        deprecated: Whether this endpoint is deprecated.
        operation_id: Custom OpenAPI operation ID.
        include_in_schema: Include in OpenAPI schema.
        name: Display name for the route.
        openapi_extra: Additional OpenAPI schema data.

    Returns:
        A decorator function that attaches the SSE route configuration.

    Raises:
        SseEndpointNotGeneratorError: If the method is not a generator function.
    """

    def wrapper(method: Callable[..., T]) -> Callable[..., T]:
        # object: inspected only, so the type guards do not narrow `method`.
        declared: object = method
        if not isasyncgenfunction(declared) and not isgeneratorfunction(declared):
            raise SseEndpointNotGeneratorError(method)
        return Route(
            path=path,
            status_code=status_code,
            tags=tags,
            dependencies=dependencies,
            summary=summary,
            description=description,
            response_description=response_description,
            responses=responses,
            deprecated=deprecated,
            methods=[HTTPMethod.GET] if methods is None else methods,
            operation_id=operation_id,
            include_in_schema=include_in_schema,
            response_class=EventSourceResponse,
            name=name,
            openapi_extra=openapi_extra,
        )(method)

    return wrapper
