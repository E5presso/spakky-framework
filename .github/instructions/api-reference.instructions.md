---
applyTo: "**/*.py"
---

# Spakky Framework API Reference

## Core API

| Decorator / Class | Import Path | Purpose |
|---|---|---|
| `@Pod(name=, scope=)` | `spakky.core.pod.annotations.pod` | Register class/function as managed bean |
| `@Primary` | `spakky.core.pod.annotations.primary` | Mark preferred implementation |
| `@Order(n)` | `spakky.core.pod.annotations.order` | Control execution order |
| `Tag` | `spakky.core.pod.annotations.tag` | Base class for custom metadata tags |
| `ITagRegistry` | `spakky.core.pod.interfaces.tag_registry` | Tag registry interface |
| `ITagRegistryAware` | `spakky.core.pod.interfaces.aware.tag_registry_aware` | Aware interface for tag registry injection |
| `IApplicationContext` | `spakky.core.pod.interfaces.application_context` | App context interface (IContainer + ITagRegistry) |
| `@Aspect()` / `@AsyncAspect()` | `spakky.core.aop.aspect` | Sync/Async aspect decorator |
| `IAsyncAspect` / `IAspect` | `spakky.core.aop.interfaces.aspect` | Aspect interfaces |
| `@Before` / `@After` / `@Around` / `@AfterReturning` / `@AfterRaising` | `spakky.core.aop.pointcut` | AOP pointcut decorators |
| `@Logging()` | `spakky.core.aspects.logging` | Built-in logging annotation |
| `@Controller` | `spakky.core.stereotype.controller` | Base controller stereotype |
| `@UseCase` | `spakky.core.stereotype.usecase` | Business logic stereotype |
| `SpakkyApplication` | `spakky.core.application.application` | App builder (`.load_plugins()` → `.add()` → `.scan()` → `.start()`) |
| `ApplicationContext` | `spakky.core.application.application_context` | IoC container context |

## Data API (spakky-data)

| Decorator / Class | Import Path | Purpose |
|---|---|---|
| `@Repository` | `spakky.data.stereotype.repository` | Data access stereotype |
| `@Transactional()` | `spakky.data.aspects.transactional` | Transaction boundary annotation |
| `AggregateCollector` | `spakky.data.persistency.aggregate_collector` | CONTEXT-scoped collector for saved aggregates |
| `IAsyncGenericRepository` | `spakky.data.persistency.repository` | Async generic repository interface |
| `AbstractAsyncTransaction` / `AbstractTransaction` | `spakky.data.persistency.transaction` | Transaction abstractions |

## Event API (spakky-event)

| Decorator / Class | Import Path | Purpose |
|---|---|---|
| `@EventHandler` / `@on_event` | `spakky.event.stereotype.event_handler` | Event handler stereotype and route |
| `IEventPublisher` / `IAsyncEventPublisher` | `spakky.event.event_publisher` | Event publish entry point (type-based routing) |
| `IEventBus` / `IAsyncEventBus` | `spakky.event.event_publisher` | Integration event send entry point (Outbox seam) |
| `IEventTransport` / `IAsyncEventTransport` | `spakky.event.event_publisher` | Actual message broker transport |
| `IEventConsumer` / `IAsyncEventConsumer` | `spakky.event.event_consumer` | Handler callback registration |
| `IEventDispatcher` / `IAsyncEventDispatcher` | `spakky.event.event_dispatcher` | In-process handler dispatch |

## Plugin API

| Decorator / Class | Import Path | Purpose |
|---|---|---|
| `@ApiController(prefix)` | `spakky.plugins.fastapi.stereotypes.api_controller` | FastAPI REST controller |
| `@CliController(group)` | `spakky.plugins.typer.stereotypes.cli_controller` | Typer CLI controller |
| `@EventHandler` / `@on_event` | `spakky.event.stereotype.event_handler` | Event handler stereotype |

## Pod Scopes

- `SINGLETON` (default): one instance per container
- `PROTOTYPE`: new instance per request
- `CONTEXT`: instance per request/context lifecycle

