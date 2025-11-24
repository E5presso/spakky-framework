"""Base route decorator and configuration for FastAPI endpoints.

Provides the core @route decorator and Route annotation class that can be
used to mark controller methods as API endpoints with full FastAPI configuration.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Sequence, TypeAlias

from fastapi import Response, params
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from spakky.core.annotation import FunctionAnnotation
from spakky.core.types import FuncT
from starlette.routing import Route as StarletteRoute

SetIntStr: TypeAlias = set[int | str]
DictIntStrAny: TypeAlias = dict[int | str, Any]


class HTTPMethod(str, Enum):
    """HTTP methods supported by FastAPI routes."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
    TRACE = "TRACE"

    def __repr__(self) -> str:
        """Return the method value for display."""
        return self.value


@dataclass
class Route(FunctionAnnotation):
    """Function annotation for marking methods as API routes.

    Stores all FastAPI route configuration including path, HTTP methods,
    response models, and OpenAPI documentation settings.

    Attributes:
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
        methods: HTTP methods this route handles.
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
    """

    path: str
    response_model: type[Any] | None = None
    status_code: int | None = None
    tags: list[str] | None = None
    dependencies: Sequence[params.Depends] | None = None
    summary: str | None = None
    description: str | None = None
    response_description: str = "Successful Response"
    responses: dict[int | str, dict[str, Any]] | None = None
    deprecated: bool | None = None
    methods: set[HTTPMethod] | list[HTTPMethod] | None = None
    operation_id: str | None = None
    response_model_include: SetIntStr | DictIntStrAny | None = None
    response_model_exclude: SetIntStr | DictIntStrAny | None = None
    response_model_by_alias: bool = True
    response_model_exclude_unset: bool = False
    response_model_exclude_defaults: bool = False
    response_model_exclude_none: bool = False
    include_in_schema: bool = True
    response_class: type[Response] = JSONResponse
    name: str | None = None
    route_class_override: type[APIRoute] | None = None
    callbacks: list[StarletteRoute] | None = None
    openapi_extra: dict[str, Any] | None = None


def route(
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
    methods: set[HTTPMethod] | list[HTTPMethod] | None = None,
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
    """Decorator to mark a controller method as an API route.

    Attaches route configuration to the method which will be registered by
    the RegisterRoutesPostProcessor during container initialization.

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
        methods: HTTP methods this route handles.
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
        A decorator function that attaches the route configuration.
    """

    def wrapper(method: FuncT) -> FuncT:
        return Route(
            path=path,
            response_model=response_model,
            status_code=status_code,
            tags=tags,
            dependencies=dependencies,
            summary=summary,
            description=description,
            response_description=response_description,
            responses=responses,
            deprecated=deprecated,
            methods=methods,
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
        )(method)

    return wrapper
