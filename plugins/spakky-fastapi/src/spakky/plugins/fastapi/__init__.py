"""FastAPI plugin for Spakky framework.

This plugin provides seamless FastAPI integration with:
- Automatic route registration via @ApiController stereotype
- Built-in error handling middleware
- Context management for request-scoped dependencies
- Support for all HTTP methods (GET, POST, PUT, DELETE, PATCH, etc.)
- WebSocket endpoint support

Example:
    >>> from spakky.plugins.fastapi.stereotypes import ApiController
    >>> from spakky.plugins.fastapi.routes import get, post
    >>>
    >>> @ApiController("/users")
    ... class UserController:
    ...     @get("/{user_id}")
    ...     async def get_user(self, user_id: int) -> User:
    ...         return await self.service.get(user_id)
"""

from spakky.core.application.plugin import Plugin
from spakky.plugins.fastapi.config import (
    SPAKKY_FASTAPI_CONFIG_ENV_PREFIX,
    FastAPIConfig,
)

PLUGIN_NAME = Plugin(name="spakky-fastapi")
"""Plugin identifier for the FastAPI integration."""

__all__ = (
    "FastAPIConfig",
    "PLUGIN_NAME",
    "SPAKKY_FASTAPI_CONFIG_ENV_PREFIX",
)
