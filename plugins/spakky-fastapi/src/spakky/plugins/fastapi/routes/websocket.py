"""WebSocket route decorator for FastAPI controllers.

Provides a decorator for marking controller methods as WebSocket endpoints
with support for FastAPI WebSocket configuration.
"""

from dataclasses import dataclass
from typing import Any
from collections.abc import Callable, Sequence

from spakky.core.common.annotation import FunctionAnnotation

from fastapi import params

type SetIntStr = set[int | str]
type DictIntStrAny = dict[int | str, Any]


@dataclass
class WebSocketRoute(FunctionAnnotation):
    """Function annotation for marking methods as WebSocket endpoints.

    Stores WebSocket route configuration including path and dependencies.

    Attributes:
        path: The URL path for this WebSocket endpoint.
        name: Display name for the WebSocket route.
        dependencies: FastAPI dependencies to inject.
    """

    path: str
    name: str | None = None
    dependencies: Sequence[params.Depends] | None = None


def websocket[T](
    path: str,
    name: str | None = None,
    dependencies: Sequence[params.Depends] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to mark a controller method as a WebSocket endpoint.

    Attaches WebSocket route configuration to the method which will be
    registered by the RegisterRoutesPostProcessor during container initialization.

    Args:
        path: The URL path for this WebSocket endpoint.
        name: Display name for the WebSocket route.
        dependencies: FastAPI dependencies to inject.

    Returns:
        A decorator function that attaches the WebSocket route configuration.
    """
    return WebSocketRoute(
        path=path,
        name=name,
        dependencies=dependencies,
    )
