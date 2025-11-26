"""Typer CLI plugin for Spakky framework.

This plugin provides seamless Typer integration with:
- Automatic command registration via @CliController stereotype
- Full async/await support for CLI commands
- Command grouping with customizable group names
- Dependency injection in CLI handlers

Example:
    >>> from spakky_typer.stereotypes import CliController, command
    >>>
    >>> @CliController("users")
    ... class UserCliController:
    ...     @command("list")
    ...     async def list_users(self) -> None:
    ...         users = await self.service.list_all()
    ...         for user in users:
    ...             print(user.name)
"""

from spakky.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-typer")
"""Plugin identifier for the Typer CLI integration."""
