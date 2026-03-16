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

Events should extend one of the event base classes from `spakky-domain`:

- Use `AbstractDomainEvent` for events within a bounded context (in-process domain events)
- Use `AbstractIntegrationEvent` for cross-boundary events (message broker integration)

When using message broker plugins (RabbitMQ / Kafka), define events as `AbstractIntegrationEvent`.

```python
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent


@immutable
class UserCreatedEvent(AbstractIntegrationEvent):
    user_id: str
    email: str


@immutable
class UserDeletedEvent(AbstractIntegrationEvent):
    user_id: str
```

### Create Event Handler

Use `@EventHandler` stereotype with `@on_event` decorators:

```python
from spakky.event.stereotype.event_handler import EventHandler, on_event


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
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

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
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

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

### Interfaces

| Interface | Description |
|-----------|-------------|
| `IEventPublisher` / `IAsyncEventPublisher` | Event publish entry point (type-based routing) |
| `IEventBus` / `IAsyncEventBus` | Integration event send entry point (Outbox seam) |
| `IEventTransport` / `IAsyncEventTransport` | Actual message broker transport |
| `IEventConsumer` / `IAsyncEventConsumer` | Handler callback registration |
| `IEventDispatcher` / `IAsyncEventDispatcher` | In-process handler dispatch |

### Implementations

| Class | Description |
|-------|-------------|
| `EventMediator` / `AsyncEventMediator` | Consumer + Dispatcher combined (in-process) |
| `EventPublisher` / `AsyncEventPublisher` | Type-based router (DomainEvent→Mediator, IntegrationEvent→EventBus) |
| `DirectEventBus` / `AsyncDirectEventBus` | Default EventBus → EventTransport delegation |
| `EventHandlerRegistrationPostProcessor` | Auto-registers `@EventHandler` methods |

### Types

| Type | Description |
|------|-------------|
| `EventRoute` | Annotation class for event routing metadata |
| `EventT_contra` | TypeVar bound to `AbstractEvent` |
| `EventHandlerCallback` | Type alias for sync event callbacks |
| `AsyncEventHandlerCallback` | Type alias for async event callbacks |

### Errors

| Class | Description |
|-------|-------------|
| `AbstractSpakkyEventError` | Base error for event operations |
| `InvalidMessageError` | Raised when message is malformed |

## Related Packages

| Package | Description |
|---------|-------------|
| `spakky-domain` | DDD building blocks including `AbstractEvent`, `AbstractDomainEvent`, `AbstractIntegrationEvent` |
| `spakky-rabbitmq` | RabbitMQ transport (`RabbitMQEventTransport`) |
| `spakky-kafka` | Kafka transport (`KafkaEventTransport`) |

## In-process Domain Event Publishing

For events within a bounded context (DomainEvents), use the in-process publisher:

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.event import IAsyncEventPublisher

# Bootstrap application (load_plugins auto-registers event components)
app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()
    .scan()
    .start()
)

# Get publisher from container
publisher = app.container.get(IAsyncEventPublisher)
await publisher.publish(UserCreatedEvent(user_id="123", email="test@example.com"))
```

### Architecture (ISP Compliant)

The in-process event system follows Interface Segregation Principle:

- **Consumer**: Registers event handlers (`register()` method)
- **Dispatcher**: Dispatches events to handlers (`dispatch()` method)
- **Mediator**: Combines both interfaces in a single implementation
- **Publisher**: Depends only on Dispatcher (not Consumer)

```
┌─────────────────┐     ┌─────────────────┐
│   Publisher     │────▶│   Dispatcher    │
└─────────────────┘     └────────┬────────┘
                                 │
                        ┌────────▼────────┐
                        │    Mediator     │
                        │ (Consumer +     │
                        │  Dispatcher)    │
                        └────────┬────────┘
                                 │
                        ┌────────▼────────┐
                        │  EventHandler   │
                        │  @on_event()    │
                        └─────────────────┘
```

## License

MIT License
