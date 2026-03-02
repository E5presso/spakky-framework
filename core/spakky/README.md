# Spakky

Core module for [Spakky Framework](https://github.com/E5presso/spakky-framework) — a Spring-inspired dependency injection framework for Python.

## Installation

```bash
pip install spakky
```

Or install with plugins:

```bash
pip install spakky[fastapi]
pip install spakky[fastapi,kafka,security]
```

## Features

- **Dependency Injection**: Powerful IoC container with constructor injection
- **Aspect-Oriented Programming**: Cross-cutting concerns with `@Aspect`
- **Plugin System**: Extensible architecture via entry points
- **Stereotypes**: Semantic annotations (`@Controller`, `@UseCase`, etc.)
- **Scopes**: Singleton, Prototype, and Context-scoped beans
- **Type-Safe**: Built with Python type hints
- **Async First**: Native async/await support

## Quick Start

### Define Pods

```python
from spakky.core.pod.annotations.pod import Pod

@Pod()
class UserRepository:
    def find_by_id(self, user_id: int) -> User | None:
        # Database query logic
        pass

@Pod()
class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    def get_user(self, user_id: int) -> User | None:
        return self.repository.find_by_id(user_id)
```

### Bootstrap Application

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
import my_app

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()
    .scan(my_app)  # or .scan() to auto-detect caller's package
    .start()
)

# Get a service from the container
user_service = app.container.get(UserService)
```

> **📘 Auto-scan**: When `scan()` is called without arguments, it automatically detects the caller's package and scans it. This also works in Docker environments where the application root may not be in `sys.path` - the framework automatically adds the necessary path.
```

## Pod Scopes

```python
from spakky.core.pod.annotations.pod import Pod

# Singleton (default) - one instance per container
@Pod(scope=Pod.Scope.SINGLETON)
class SingletonService:
    pass

# Prototype - new instance on each request
@Pod(scope=Pod.Scope.PROTOTYPE)
class PrototypeService:
    pass

# Context - scoped to request/context lifecycle
@Pod(scope=Pod.Scope.CONTEXT)
class ContextScopedService:
    pass
```

## Qualifiers

```python
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.annotations.primary import Primary

# Named qualifier
@Pod(name="mysql")
class MySQLRepository(IRepository):
    pass

@Pod(name="postgres")
class PostgresRepository(IRepository):
    pass

# Primary - preferred when multiple implementations exist
@Primary()
@Pod()
class DefaultRepository(IRepository):
    pass
```

## Stereotypes

```python
from spakky.core.stereotype.controller import Controller
from spakky.core.stereotype.usecase import UseCase

@Controller()
class UserController:
    """Groups related handlers together."""
    pass

@UseCase()
class CreateUserUseCase:
    """Encapsulates business logic."""
    pass
```

## Aspect-Oriented Programming

```python
from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.aop.pointcut import Before, After, Around
from spakky.core.pod.annotations.order import Order
from spakky.core.aspects.logging import Logging

# Create custom aspect
@Order(0)
@Aspect()
class LoggingAspect(IAspect):
    @Before(lambda m: Logging.exists(m))
    def before(self, *args, **kwargs) -> None:
        print("Before method execution")

    @After(lambda m: Logging.exists(m))
    def after(self, *args, **kwargs) -> None:
        print("After method execution")

# Apply to methods
@Pod()
class MyService:
    @Logging()
    def my_method(self) -> str:
        return "Hello"
```

### Async Aspects

```python
from spakky.core.aop.aspect import AsyncAspect
from spakky.core.aop.interfaces.aspect import IAsyncAspect
from spakky.core.aop.pointcut import Around

@Order(0)
@AsyncAspect()
class TimingAspect(IAsyncAspect):
    @Around(lambda m: hasattr(m, "__timed__"))
    async def around_async(self, joinpoint, *args, **kwargs):
        start = time.time()
        result = await joinpoint(*args, **kwargs)
        elapsed = time.time() - start
        print(f"Execution time: {elapsed:.2f}s")
        return result
```

## Built-in Aspects

```python
from spakky.core.aspects.logging import Logging

@Pod()
class OrderService:
    @Logging()  # Automatic logging
    async def create_order(self, order: Order) -> Order:
        return await self.repository.save(order)
```

## Context Management

ApplicationContext provides context-scoped value storage:

```python
from spakky.core.application.application_context import ApplicationContext

context = ApplicationContext()

# Get unique context ID
context_id = context.get_context_id()

# Store and retrieve context values
context.set_context_value("user_id", 123)
user_id = context.get_context_value("user_id")  # Returns 123

# Clear context (except system-managed keys)
context.clear_context()
```

> **⚠️ Note**: System-managed keys like `"__spakky_context_id__"` cannot be overridden via `set_context_value()`.

## Tag Registry

ApplicationContext implements `ITagRegistry` for managing custom metadata tags. Tags are dataclass-based annotations that can be registered and queried at runtime.

### Defining Custom Tags

```python
from dataclasses import dataclass
from spakky.core.pod.annotations.tag import Tag

@dataclass(eq=False)
class MyCustomTag(Tag):
    """Custom tag for marking specific components."""
    category: str = ""
```

### Registering and Querying Tags

```python
from spakky.core.application.application_context import ApplicationContext

context = ApplicationContext()

# Register tags
tag = MyCustomTag(category="database")
context.register_tag(tag)

# Check if tag exists
exists = context.contains_tag(tag)  # True

# Get all tags
all_tags = context.tags  # frozenset of all registered tags

# Filter tags with selector
db_tags = context.list_tags(lambda t: isinstance(t, MyCustomTag) and t.category == "database")
```

### Tag Registry Aware Pods

Pods can receive the tag registry via `ITagRegistryAware`:

```python
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.aware.tag_registry_aware import ITagRegistryAware
from spakky.core.pod.interfaces.tag_registry import ITagRegistry

@Pod()
class SchemaRegistry(ITagRegistryAware):
    def __init__(self) -> None:
        self._tag_registry: ITagRegistry | None = None

    def set_tag_registry(self, tag_registry: ITagRegistry) -> None:
        self._tag_registry = tag_registry
        # Access registered tags
        for tag in tag_registry.list_tags(MyCustomTag.exists):
            # Process tags...
            pass
```

## Plugin System

Plugins extend framework functionality through entry points.

### Creating a Plugin

1. Create package with `uv init --lib spakky-<name>` in `plugins/` directory
2. Register in root `pyproject.toml`'s `[tool.uv.workspace]` members
3. Define entry point in plugin's `pyproject.toml`:

```toml
[project.entry-points."spakky.plugins"]
spakky-<name> = "spakky.plugins.<name>.main:initialize"
```

4. Implement initialization function:

```python
# In spakky.plugins.<name>/main.py
from spakky.core.application.application import SpakkyApplication

def initialize(app: SpakkyApplication) -> None:
    # Register plugin components
    pass
```

See [Contributing Guide](../../CONTRIBUTING.md#-plugin-development) for detailed instructions.

## Available Plugins

| Plugin | Description |
|--------|-------------|
| [`spakky-fastapi`](https://pypi.org/project/spakky-fastapi/) | FastAPI integration |
| [`spakky-kafka`](https://pypi.org/project/spakky-kafka/) | Apache Kafka event system |
| [`spakky-rabbitmq`](https://pypi.org/project/spakky-rabbitmq/) | RabbitMQ event system |
| [`spakky-security`](https://pypi.org/project/spakky-security/) | Security utilities |
| [`spakky-typer`](https://pypi.org/project/spakky-typer/) | Typer CLI integration |

## Core Modules

| Module | Description |
|--------|-------------|
| `spakky.core.pod` | Dependency injection container and annotations |
| `spakky.core.aop` | Aspect-oriented programming framework |
| `spakky.core.application` | Application context and lifecycle |
| `spakky.core.stereotype` | Semantic stereotype annotations |
| `spakky.core.aspects` | Built-in aspects (Logging) |
| `spakky.core.service` | Service layer components |
| `spakky.core.common` | Core utilities (annotation, types, metadata) |
| `spakky.core.utils` | Utility functions |

## Related Packages

| Package | Description |
|---------|-------------|
| [`spakky-domain`](https://pypi.org/project/spakky-domain/) | DDD building blocks (Entity, AggregateRoot, ValueObject, Event) |
| [`spakky-event`](https://pypi.org/project/spakky-event/) | Event handling (`@EventHandler` stereotype) |

## License

MIT
