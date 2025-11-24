"""FastAPI route decorators.

Provides HTTP method decorators (@get, @post, @put, @delete, etc.) and
@websocket decorator for marking controller methods as API endpoints.
"""

from .delete import delete
from .get import get
from .head import head
from .options import options
from .patch import patch
from .post import post
from .put import put
from .route import route
from .websocket import websocket

__all__ = [
    "delete",
    "get",
    "head",
    "options",
    "patch",
    "post",
    "put",
    "route",
    "websocket",
]
