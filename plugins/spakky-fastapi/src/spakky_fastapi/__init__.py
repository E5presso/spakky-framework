"""FastAPI plugin for Spakky framework.

This plugin provides seamless FastAPI integration with:
- Automatic route registration via @ApiController stereotype
- Built-in error handling middleware
- Context management for request-scoped dependencies
- Support for all HTTP methods (GET, POST, PUT, DELETE, PATCH, etc.)
- WebSocket endpoint support

Example:
    >>> from spakky_fastapi.stereotypes import ApiController
    >>> from spakky_fastapi.routes import get, post
    >>>
    >>> @ApiController("/users")
    ... class UserController:
    ...     @get("/{user_id}")
    ...     async def get_user(self, user_id: int) -> User:
    ...         return await self.service.get(user_id)
"""

from spakky.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-fastapi")
"""Plugin identifier for the FastAPI integration."""
