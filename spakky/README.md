# Spakky

Core module for [Spakky Framework](https://github.com/E5presso/spakky-framework) - a Spring-inspired dependency injection framework for Python.

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
from spakky.pod.annotations.pod import Pod

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
from spakky.application.application import SpakkyApplication
from spakky.application.application_context import ApplicationContext
import my_app

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()
    .scan(my_app)
    .start()
)

# Get a service from the container
user_service = app.container.get(UserService)
```

## Pod Scopes

```python
from spakky.pod.annotations.pod import Pod

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
from spakky.pod.annotations.pod import Pod
from spakky.pod.annotations.primary import Primary

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
from spakky.stereotype.controller import Controller
from spakky.stereotype.usecase import UseCase

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
from spakky.aop.aspect import Aspect, AsyncAspect
from spakky.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.aop.pointcut import Before, After, Around
from spakky.pod.annotations.order import Order
from spakky.aspects.logging import Logging

# Create custom aspect
@Order(0)
@Aspect()
class LoggingAspect(IAspect):
    @Before(lambda m: Logging.exists(m))
    def before_log(self, *args, **kwargs) -> None:
        print("Before method execution")

    @After(lambda m: Logging.exists(m))
    def after_log(self, *args, **kwargs) -> None:
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
from spakky.aop.aspect import AsyncAspect
from spakky.aop.interfaces.aspect import IAsyncAspect
from spakky.aop.pointcut import Around

@Order(0)
@AsyncAspect()
class TimingAspect(IAsyncAspect):
    @Around(lambda m: hasattr(m, "__timed__"))
    async def time_execution(self, joinpoint, *args, **kwargs):
        start = time.time()
        result = await joinpoint(*args, **kwargs)
        elapsed = time.time() - start
        print(f"Execution time: {elapsed:.2f}s")
        return result
```

## Built-in Aspects

```python
from spakky.aspects.logging import Logging
from spakky.aspects.transactional import Transactional

@Pod()
class OrderService:
    @Logging()  # Automatic logging
    @Transactional()  # Transaction management
    async def create_order(self, order: Order) -> Order:
        return await self.repository.save(order)
```

## Plugin System

Plugins extend framework functionality:

```python
# In pyproject.toml
[project.entry-points."spakky.plugins"]
my-plugin = "my_plugin.main:initialize"

# In my_plugin/main.py
from spakky.application.application import SpakkyApplication

def initialize(app: SpakkyApplication) -> None:
    # Register plugin components
    pass
```

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
| `spakky.pod` | Dependency injection container and annotations |
| `spakky.aop` | Aspect-oriented programming framework |
| `spakky.application` | Application context and lifecycle |
| `spakky.stereotype` | Semantic stereotype annotations |
| `spakky.aspects` | Built-in aspects (Logging, Transactional) |
| `spakky.domain` | Domain interfaces and abstractions |
| `spakky.service` | Service layer components |
| `spakky.core` | Core utilities (proxy, annotation, types) |

## License

MIT
