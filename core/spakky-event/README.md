# Spakky Event

Event handling stereotype for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-event
```

## Features

- **`@EventHandler`**: Stereotype for event handler classes
- **`@on_event`**: Decorator for marking methods as event handlers
- **Type-safe**: Full type hint support for event types
- **Async support**: Native async/await for event processing

## Quick Start

### Define Events

Events should extend `AbstractDomainEvent` from `spakky-ddd`:

```python
from dataclasses import dataclass

from spakky_ddd.models.event import AbstractDomainEvent


@dataclass
class UserCreatedEvent(AbstractDomainEvent):
    user_id: str
    email: str


@dataclass
class UserDeletedEvent(AbstractDomainEvent):
    user_id: str
```

### Create Event Handler

Use `@EventHandler` stereotype with `@on_event` decorators:

```python
from spakky_event.stereotype.event_handler import EventHandler, on_event


@EventHandler()
class UserEventHandler:
    def __init__(self, notification_service: NotificationService) -> None:
        self.notification_service = notification_service

    @on_event(UserCreatedEvent)
    async def on_user_created(self, event: UserCreatedEvent) -> None:
        await self.notification_service.send_welcome_email(event.email)

    @on_event(UserDeletedEvent)
    async def on_user_deleted(self, event: UserDeletedEvent) -> None:
        await self.notification_service.send_goodbye_email(event.user_id)
```

### Integration with Message Brokers

The `@EventHandler` stereotype works with Spakky's message broker plugins:

#### RabbitMQ

```bash
pip install spakky-rabbitmq
```

```python
from spakky.application.application import SpakkyApplication
from spakky.application.application_context import ApplicationContext

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()  # Loads spakky-rabbitmq plugin
    .scan()
    .start()
)
```

#### Kafka

```bash
pip install spakky-kafka
```

```python
from spakky.application.application import SpakkyApplication
from spakky.application.application_context import ApplicationContext

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()  # Loads spakky-kafka plugin
    .scan()
    .start()
)
```

## API Reference

### Stereotypes

| Decorator | Description |
|-----------|-------------|
| `@EventHandler()` | Marks a class as an event handler (extends `@Pod`) |
| `@on_event(EventType)` | Marks a method as handler for specific event type |

### Types

| Type | Description |
|------|-------------|
| `EventRoute` | Annotation class for event routing metadata |
| `DomainEventT` | Type variable bound to `AbstractDomainEvent` |
| `IEventHandlerCallback` | Type alias for event handler callbacks |

## License

MIT License
