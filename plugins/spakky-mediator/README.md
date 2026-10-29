# Spakky Mediator

`spakky-mediator` is the optional in-process domain event consumer and dispatcher provider. `spakky-event` owns event contracts, publishing, transactional publication and handler-provider validation. Installing event support does not select a local consumer.

## Installation and plugin selection

```bash
uv add spakky-event spakky-mediator
# Or use the explicit convenience extra:
uv add 'spakky[mediator]'
```

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.application.plugin import Plugin

application = SpakkyApplication(ApplicationContext()).load_plugins(include={
    Plugin(name="spakky-data"),
    Plugin(name="spakky-event"),
    Plugin(name="spakky-mediator"),
    Plugin(name="spakky-tracing"),
})
```

This configures plugin loading. Keep the application's transaction provider and other plugins in the include set, register or scan application Pods, then call `start()`. Calling `load_plugins()` without an include set loads every installed plugin, including mediator when installed.

## Direct dispatch example

This standalone example uses the synchronous mediator without a broker or an application container:

```python
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractDomainEvent
from spakky.plugins.mediator.mediator import EventMediator


@immutable
class UserCreated(AbstractDomainEvent):
    user_id: str


def handle_user_created(event: UserCreated) -> None:
    print(f"User created: {event.user_id}")


mediator = EventMediator()
mediator.register(UserCreated, handle_user_created)
mediator.dispatch(UserCreated(user_id="123"))
```

In an application, load the plugin to register handlers automatically and inject `IEventPublisher` / `IAsyncEventPublisher` from `spakky.event.event_publisher` for type-based routing.

## Handler registration

The plugin registers `EventMediator`, `AsyncEventMediator` and `EventHandlerRegistrationPostProcessor`. It registers only `AbstractDomainEvent` routes. Broker plugins own integration event routes independently, so loading mediator and Kafka together does not require a global `IEventConsumer` binding.

The role-specific consumer contracts are defined in `spakky.event.event_consumer`: `IDomainEventConsumer` and `IAsyncDomainEventConsumer` for local handlers, and `IIntegrationEventConsumer` and `IAsyncIntegrationEventConsumer` for broker handlers. The generic consumer interfaces remain available for existing application ports; applications with both provider categories should request a specific role.

An application declaring a handler without the matching synchronous/asynchronous provider fails startup with `EventHandlerProviderUnavailableError`. Publishing a domain event without a dispatcher raises `DomainEventDispatcherUnavailableError`; it never silently drops the event.

## Migration

Starting with **9.0.0**, install and explicitly select `spakky-mediator` where local domain dispatch is required. See the [9.0 migration guide](../../docs/guides/events-migration.md) for installation extras, startup configuration and provider errors. Update concrete imports:

```python
from spakky.plugins.mediator.mediator import EventMediator, AsyncEventMediator
from spakky.plugins.mediator.post_processor import EventHandlerRegistrationPostProcessor
```

The historical `spakky.event.mediator` implementations and `spakky.event.post_processor.EventHandlerRegistrationPostProcessor` no longer belong to event core. Broker-only services need no mediator installation. No mediator dependency is hidden in the `event` extra.

## Explicit deferral

A local handler may raise `spakky.event.EventDeferredError` before effects (or after
its transaction rolls back). The mediator propagates this intentional deferral to
the publisher instead of treating it as an ordinary resilient-handler error. It
does not create a local durable retry queue. Kafka implements broker redelivery
through partition pause/rewind, continuous polling and rebalance-aware timers.
