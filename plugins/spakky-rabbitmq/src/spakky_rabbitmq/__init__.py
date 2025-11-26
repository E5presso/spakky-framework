"""RabbitMQ plugin for Spakky framework.

This plugin provides seamless RabbitMQ integration with:
- Domain event publishing via IEventPublisher interface
- Automatic event handler registration via @EventHandler stereotype
- Background consumer service for message processing
- Configurable connection and queue settings

Example:
    >>> from spakky_rabbitmq.event import IEventPublisher
    >>> from spakky.stereotype.event_handler import EventHandler, on_event
    >>>
    >>> @EventHandler()
    ... class UserEventHandler:
    ...     @on_event(UserCreatedEvent)
    ...     async def on_user_created(self, event: UserCreatedEvent) -> None:
    ...         await self.notification.send_welcome(event.email)
"""

from spakky.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-rabbitmq")
"""Plugin identifier for the RabbitMQ integration."""
