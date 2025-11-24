"""OPTIONS route decorator for FastAPI controllers.

Provides a convenience decorator for marking controller methods as HTTP OPTIONS
endpoints with full FastAPI configuration support.
"""

from typing import Any, Callable, Sequence

from fastapi import Response, params
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from spakky.core.types import FuncT
from starlette.routing import Route as StarletteRoute

from spakky_fastapi.routes.route import DictIntStrAny, HTTPMethod, SetIntStr, route


def options(
    path: str,
    response_model: type[Any] | None = None,
    status_code: int | None = None,
    tags: list[str] | None = None,
    dependencies: Sequence[params.Depends] | None = None,
    summary: str | None = None,
    description: str | None = None,
    response_description: str = "Successful Response",
    responses: dict[int | str, dict[str, Any]] | None = None,
    deprecated: bool | None = None,
    operation_id: str | None = None,
    response_model_include: SetIntStr | DictIntStrAny | None = None,
    response_model_exclude: SetIntStr | DictIntStrAny | None = None,
    response_model_by_alias: bool = True,
    response_model_exclude_unset: bool = False,
    response_model_exclude_defaults: bool = False,
    response_model_exclude_none: bool = False,
    include_in_schema: bool = True,
    response_class: type[Response] = JSONResponse,
    name: str | None = None,
    route_class_override: type[APIRoute] | None = None,
    callbacks: list[StarletteRoute] | None = None,
    openapi_extra: dict[str, Any] | None = None,
) -> Callable[[FuncT], FuncT]:
    """Decorator to mark a controller method as an HTTP OPTIONS endpoint.

    Convenience wrapper around @route that automatically sets the HTTP method
    to OPTIONS. Supports all FastAPI route configuration options.

    Args:
        path: The URL path for this route.
        response_model: Pydantic model for response serialization.
        status_code: HTTP status code for successful responses.
        tags: OpenAPI tags for grouping endpoints.
        dependencies: FastAPI dependencies to inject.
        summary: Short summary for OpenAPI documentation.
        description: Detailed description for OpenAPI documentation.
        response_description: Description of successful response.
        responses: Additional response schemas for OpenAPI.
        deprecated: Whether this endpoint is deprecated.
        operation_id: Custom OpenAPI operation ID.
        response_model_include: Fields to include in response model.
        response_model_exclude: Fields to exclude from response model.
        response_model_by_alias: Use field aliases in response.
        response_model_exclude_unset: Exclude unset fields from response.
        response_model_exclude_defaults: Exclude fields with default values.
        response_model_exclude_none: Exclude None values from response.
        include_in_schema: Include in OpenAPI schema.
        response_class: FastAPI response class to use.
        name: Display name for the route.
        route_class_override: Custom APIRoute class.
        callbacks: OpenAPI callbacks configuration.
        openapi_extra: Additional OpenAPI schema data.

    Returns:
        A decorator function that marks the method as an OPTIONS endpoint.
    """
    return route(
        path=path,
        methods=[HTTPMethod.OPTIONS],
        response_model=response_model,
        status_code=status_code,
        tags=tags,
        dependencies=dependencies,
        summary=summary,
        description=description,
        response_description=response_description,
        responses=responses,
        deprecated=deprecated,
        operation_id=operation_id,
        response_model_include=response_model_include,
        response_model_exclude=response_model_exclude,
        response_model_by_alias=response_model_by_alias,
        response_model_exclude_unset=response_model_exclude_unset,
        response_model_exclude_defaults=response_model_exclude_defaults,
        response_model_exclude_none=response_model_exclude_none,
        include_in_schema=include_in_schema,
        response_class=response_class,
        name=name,
        route_class_override=route_class_override,
        callbacks=callbacks,
        openapi_extra=openapi_extra,
    )
