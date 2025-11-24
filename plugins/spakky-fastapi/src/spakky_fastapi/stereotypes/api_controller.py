"""API controller stereotype for FastAPI route grouping.

Provides the @ApiController stereotype for marking classes as FastAPI REST
controllers with automatic route registration and prefix configuration.
"""

from dataclasses import dataclass
from enum import Enum

from spakky.stereotype.controller import Controller


@dataclass(eq=False)
class ApiController(Controller):
    """Stereotype for FastAPI REST API controllers.

    Marks a class as an API controller with automatic route registration.
    Methods decorated with @get, @post, etc. will be registered as FastAPI
    endpoints with the specified prefix.

    Attributes:
        prefix: URL prefix for all routes in this controller.
        tags: OpenAPI tags for grouping endpoints in documentation.
    """

    prefix: str
    """URL prefix prepended to all routes in this controller."""

    tags: list[str | Enum] | None = None
    """OpenAPI tags for grouping and organizing endpoints in documentation."""
