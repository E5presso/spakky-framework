# Spakky Framework - AI Coding Instructions

## Architecture Overview

Spakky is a Spring-inspired dependency injection framework for Python with AOP and plugin system:

- **Core (`core/`)**: DI/IoC container, AOP aspects, DDD building blocks, event handling, and application context
- **Plugins (`plugins/`)**: Framework extensions (FastAPI, RabbitMQ, Typer, Security, Kafka)
- **Monorepo structure**: Uses `uv` workspace with shared tooling and cross-package dependencies
- **Python version**: Requires Python 3.11+
- **Build system**: Uses `uv` for dependency management and `uv_build` for packaging

## Project Structure

```
spakky-framework/
├── core/
│   ├── spakky/                    # Core DI/IoC framework
│   │   ├── src/spakky/core/
│   │   │   ├── aop/               # Aspect-Oriented Programming
│   │   │   ├── application/       # Application context and lifecycle
│   │   │   ├── aspects/           # Built-in aspects (Logging)
│   │   │   ├── common/            # Common utilities (annotation, types, metadata)
│   │   │   ├── pod/               # Dependency injection container
│   │   │   ├── service/           # Service layer components
│   │   │   ├── stereotype/        # Base stereotypes (Controller, UseCase, etc.)
│   │   │   └── utils/             # Utility functions
│   │   └── tests/
│   │
│   ├── spakky-domain/             # DDD building blocks
│   │   ├── src/spakky/domain/
│   │   │   ├── application/       # Command and Query interfaces (CQRS)
│   │   │   └── models/            # Entity, AggregateRoot, ValueObject, Event
│   │   └── tests/
│   │
│   ├── spakky-data/               # Data access abstractions
│   │   ├── src/spakky/data/
│   │   │   ├── persistency/       # Repository and Transaction
│   │   │   └── external/          # External service proxy
│   │   └── tests/
│   │
│   └── spakky-event/              # Event handling
│       ├── src/spakky/event/
│       │   ├── stereotype/        # @EventHandler stereotype
│       │   ├── event_publisher.py # IEventPublisher, IAsyncEventPublisher
│       │   ├── event_consumer.py  # IEventConsumer, IAsyncEventConsumer
│       │   └── error.py           # Event-related errors
│       └── tests/
│
└── plugins/
    ├── spakky-fastapi/            # FastAPI integration
    │   ├── src/spakky/plugins/fastapi/
    │   │   ├── middlewares/       # FastAPI middleware
    │   │   ├── post_processors/   # Route registration post-processors
    │   │   ├── routes/            # Route decorators (get, post, etc.)
    │   │   └── stereotypes/       # ApiController stereotype
    │   └── tests/
    │
    ├── spakky-rabbitmq/           # RabbitMQ event system
    │   ├── src/spakky/plugins/rabbitmq/
    │   │   ├── common/            # Configuration and constants
    │   │   └── event/             # Event publisher/consumer
    │   └── tests/
    │
    ├── spakky-security/           # Security utilities
    │   ├── src/spakky/plugins/security/
    │   │   ├── cryptography/      # Encryption/decryption
    │   │   └── password/          # Password hashing
    │   └── tests/
    │
    ├── spakky-typer/              # CLI integration
    │   ├── src/spakky/plugins/typer/
    │   │   ├── stereotypes/       # CliController stereotype
    │   │   └── utils/             # Asyncio utilities
    │   └── tests/
    │
    └── spakky-kafka/              # Apache Kafka event system
        ├── src/spakky/plugins/kafka/
        │   ├── common/            # Configuration and constants
        │   └── event/             # Event publisher/consumer
        └── tests/
```

## Key Concepts

### Pod System (DI/IoC)

- **`@Pod`** decorator registers classes/functions as managed beans in the IoC container
- **Constructor injection**: Automatic dependency resolution via type hints
- **Scopes**:
  - `SINGLETON` (default): One instance per container
  - `PROTOTYPE`: New instance on each request
  - `CONTEXT`: Scoped to request/context lifecycle
- **Qualifiers**: Use `name` parameter for disambiguation
- **`@Primary`**: Mark preferred implementation when multiple candidates exist
- **Method injection**: Dependencies resolved automatically when methods are called

```python
from spakky.core.pod.annotations.pod import Pod

@Pod(name="user_service", scope=Pod.Scope.SINGLETON)
class UserService:
    def __init__(self, repository: IUserRepository) -> None:
        self.repository = repository
```

### Stereotypes

Stereotypes extend `@Pod` with semantic meaning and additional behaviors:

- **`@Controller`**: Base stereotype for grouping related handlers (from `spakky.core.stereotype.controller`)
- **`@UseCase`**: Encapsulates business logic (from `spakky.core.stereotype.usecase`)
- **`@ApiController(prefix)`**: FastAPI REST controllers with route registration (from `spakky.plugins.fastapi.stereotypes.api_controller`)
- **`@CliController(group_name)`**: Typer CLI controllers (from `spakky.plugins.typer.stereotypes.cli_controller`)
- **`@EventHandler`**: Event handlers for RabbitMQ/Kafka (from `spakky.event.stereotype.event_handler`)

All stereotypes are automatically registered as Pods and support dependency injection.

```python
from spakky.plugins.fastapi.stereotypes.api_controller import ApiController
from spakky.plugins.fastapi.routes import get, post

@ApiController("/users")
class UserController:
    def __init__(self, use_case: UserUseCase) -> None:
        self.use_case = use_case

    @get("/{id}")
    async def get_user(self, id: int) -> User:
        return await self.use_case.get_user(id)
```

### AOP (Aspect-Oriented Programming)

- **`@Aspect()`**: Decorator for synchronous aspects
- **`@AsyncAspect()`**: Decorator for asynchronous aspects
- **Pointcuts**: Define when advice should be applied
  - `@Before(predicate)`: Before method execution
  - `@After(predicate)`: After method execution (always)
  - `@Around(predicate)`: Wrap method execution
  - `@AfterReturning(predicate)`: After successful return
  - `@AfterRaising(predicate)`: After exception raised
- **Built-in aspects**:
  - `@Logging()`: Automatic logging of method calls (from `spakky.core.aspects.logging`)
- **Order control**: Use `@Order(n)` to control aspect execution order

```python
from inspect import iscoroutinefunction
from logging import getLogger
from typing import Any

from spakky.core.aop.aspect import AsyncAspect
from spakky.core.aop.interfaces.aspect import IAsyncAspect
from spakky.core.aop.pointcut import Around
from spakky.core.aspects.logging import Logging
from spakky.core.common.types import AsyncFunc
from spakky.core.pod.annotations.order import Order

logger = getLogger(__name__)

@Order(0)
@AsyncAspect()
class CustomLoggingAspect(IAsyncAspect):
    @Around(lambda x: Logging.exists(x) and iscoroutinefunction(x))
    async def around_async(self, joinpoint: AsyncFunc, *args: Any, **kwargs: Any) -> Any:
        logger.info(f"Calling {joinpoint.__name__}")
        result = await joinpoint(*args, **kwargs)
        logger.info(f"Finished {joinpoint.__name__}")
        return result
```

### Plugin System

Plugins extend framework functionality through a formal plugin architecture:

- **Entry points**: Defined in `pyproject.toml` under `[project.entry-points."spakky.plugins"]`
- **Initialization**: Each plugin exports an `initialize(app: SpakkyApplication)` function
- **Post-processors**: Modify container behavior via `IPostProcessor` interface

```toml
# In plugin's pyproject.toml
[project.entry-points."spakky.plugins"]
spakky-fastapi = "spakky.plugins.fastapi.main:initialize"
```

```python
# In spakky.plugins.fastapi/main.py
from spakky.core.application.application import SpakkyApplication

def initialize(app: SpakkyApplication) -> None:
    """Plugin initialization function"""
    # Register plugin-specific Pods, post-processors, etc.
    pass
```

## Development Patterns

### Application Bootstrap

The application lifecycle follows a builder pattern:

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.aspects import AsyncLoggingAspect, LoggingAspect

# Build and start application
app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()                    # Load all plugins from entry points
    .add(AsyncLoggingAspect)           # Register async logging aspect
    .add(LoggingAspect)                # Register sync logging aspect
    .scan(my_package)                  # Scan package for @Pod annotated classes
    .start()                           # Initialize container and aspects
)

# Access container
user_service = app.container.get(UserService)
```

**Key methods**:

- `load_plugins()`: Discovers and loads all plugins via entry points
- `scan(module)`: Scans module for `@Pod`, `@Controller`, `@UseCase`, etc. If no argument is provided, automatically scans the caller's package.
- `add(pod_type)`: Manually registers a Pod type (including aspects)
- `start()`: Finalizes container setup and runs post-processors

> **Docker Environment Support**: When `scan()` is called without arguments, it uses `ensure_importable()` to automatically add the caller's package parent directory to `sys.path` if needed. This ensures the framework works correctly in Docker containers where the application root may not be in `sys.path`.

### RabbitMQ Event Handlers

The RabbitMQ plugin provides event-driven architecture support.

**Configuration**: Set environment variables with the `spakky.plugins.rabbitmq__` prefix (note the double underscore at the end):

```bash
export spakky.plugins.rabbitmq__USE_SSL="false"
export spakky.plugins.rabbitmq__HOST="localhost"
export spakky.plugins.rabbitmq__PORT="5672"
export spakky.plugins.rabbitmq__USER="guest"
export spakky.plugins.rabbitmq__PASSWORD="guest"
export spakky.plugins.rabbitmq__EXCHANGE_NAME="my-exchange"
```

**Event Consuming**: Use `@EventHandler` stereotype with `@on_event` decorators.

```python
from spakky.event.stereotype.event_handler import EventHandler, on_event
from spakky.domain.models.event import AbstractDomainEvent

class UserCreatedEvent(AbstractDomainEvent):
    user_id: int
    email: str

@EventHandler()
class UserEventHandler:
    def __init__(self, notification_service: NotificationService) -> None:
        self.notification_service = notification_service

    @on_event(UserCreatedEvent)
    async def on_user_created(self, event: UserCreatedEvent) -> None:
        await self.notification_service.send_welcome_email(event.email)
```

### Kafka Event Handlers

The Kafka plugin provides a similar event-driven pattern to RabbitMQ.

**Configuration**: Set environment variables with the `SPAKKY_KAFKA__` prefix (note the double underscore at the end):

```bash
export SPAKKY_KAFKA__GROUP_ID="my-consumer-group"
export SPAKKY_KAFKA__CLIENT_ID="my-app"
export SPAKKY_KAFKA__BOOTSTRAP_SERVERS="localhost:9092"
export SPAKKY_KAFKA__AUTO_OFFSET_RESET="earliest"
```

### Typer CLI Controllers

Use `@CliController(group_name)` with `@command` decorators:

```python
from spakky.plugins.typer.stereotypes.cli_controller import CliController, command

@CliController("user")
class UserCliController:
    def __init__(self, user_service: UserService) -> None:
        self.user_service = user_service

    @command("create")
    async def create_user(self, email: str, username: str) -> None:
        """Create a new user"""
        user = await self.user_service.create(email, username)
        print(f"Created user: {user.id}")
```

## Build & Test Commands

### Dependency Installation

This monorepo uses `uv` workspaces.

```bash
# From workspace root - install everything
uv sync --all-packages --all-extras

# From a sub-package directory - install only that package
cd plugins/spakky-fastapi
uv sync --all-extras
```

### Opening Sub-Projects Independently

Each sub-project can be opened independently in VS Code while still using the root virtual environment:

1. **VS Code Settings**: Each sub-project has `.vscode/settings.json` with `python.defaultInterpreterPath` pointing to the root's `.venv`:

   ```json
   {
     "python.defaultInterpreterPath": "${workspaceFolder}/../../.venv/bin/python"
   }
   ```

2. **Pre-commit Hooks**: All hooks use conditional path handling to work both from monorepo root and standalone:

   ```yaml
   # Works from root: cd core/spakky && run
   # Works standalone: run in current directory
   entry: bash -c 'if [ -d "core/spakky" ]; then cd core/spakky; fi && uv run pyrefly check'
   ```

3. **Pre-push Hooks**: Each sub-project has a `pytest` hook registered in the `pre-push` stage.

### Running Tests

**IMPORTANT**: This monorepo does NOT support running tests from the root directory. Each package manages its own tests independently.

```bash
# ❌ Wrong - This will FAIL with import errors
cd /path/to/spakky-framework
uv run pytest

# ✅ Correct - Run tests from each package directory
cd core/spakky
uv run pytest

cd plugins/spakky-fastapi
uv run pytest

cd plugins/spakky-rabbitmq
uv run pytest

# etc. for each package
```

**Available packages for testing**:
- `core/spakky/` - Core framework
- `core/spakky-domain/` - DDD building blocks
- `core/spakky-event/` - Event handling
- `core/spakky-data/` - Data access layer (WIP)
- `plugins/spakky-fastapi/` - FastAPI plugin
- `plugins/spakky-rabbitmq/` - RabbitMQ plugin
- `plugins/spakky-kafka/` - Kafka plugin
- `plugins/spakky-security/` - Security plugin
- `plugins/spakky-typer/` - Typer CLI plugin

### Test Style Guidelines

- **Function-based tests**: Use plain functions, not classes. Avoid wrapping tests in `class TestXxx:`.
- **Naming convention**: Use `test_<function_name>_<scenario>_expect_<result>` pattern.
- **Docstrings**: Each test function should have a docstring explaining what it tests.

```python
# ✅ Correct - Function-based test
def test_ensure_importable_when_parent_in_sys_path() -> None:
    """Test that nothing happens when parent is already in sys.path."""
    ...

# ❌ Wrong - Class-based test
class TestEnsureImportable:
    def test_when_parent_in_sys_path(self) -> None:
        ...
```

## AI Documentation Maintenance Rules

**CRITICAL INSTRUCTION FOR AI AGENTS:**

When updating this documentation (`.github/copilot-instructions.md`), you MUST adhere to the following strict verification process:

1.  **Code-First Verification**: Every statement in this document must be backed by actual code in the repository. Do not assume features exist based on common patterns or previous knowledge.
2.  **Cross-Reference**: Before writing any documentation about a feature (e.g., a decorator, a configuration prefix), you must find the exact line of code defining it.
3.  **No Hallucinations**: If you cannot find the code implementation, do not document it.
4.  **Full Scope Scan**: You must explore the relevant package structure, module exports, and source code files (`.py`) to validate your findings.
5.  **Mandatory Clause Preservation**: This section ("AI Documentation Maintenance Rules") must be preserved in all future versions of this document.
6.  **Global Documentation Synchronization**: Any changes to the codebase (APIs, configuration, behavior) MUST be immediately reflected in all relevant Markdown files (README.md, CONTRIBUTING.md, etc.) across the repository. **Note**: CHANGELOG.md is auto-generated by `commitizen bump`, so do NOT manually update it.
7.  **Sub-Package Documentation**: When updating documentation, you MUST also check and update README.md files in ALL sub-packages. This includes:
    - **Core packages**: `core/spakky/README.md`, `core/spakky-domain/README.md`, `core/spakky-event/README.md`, `core/spakky-data/README.md`
    - **Plugin packages**: `plugins/spakky-fastapi/README.md`, `plugins/spakky-rabbitmq/README.md`, `plugins/spakky-kafka/README.md`, `plugins/spakky-security/README.md`, `plugins/spakky-typer/README.md`
    - Each sub-package README must have accurate import paths, API references, and usage examples that match the current codebase.

## AI Tool Usage Guidelines

**CRITICAL INSTRUCTION FOR AI AGENTS:**

When performing actions in this repository, follow these guidelines:

1.  **Prefer Integrated Tools Over Terminal**: When a dedicated tool is available (e.g., `runTests` for running tests, `get_errors` for checking errors), always use it instead of running terminal commands. Integrated tools provide better structured output and are more reliable.

2.  **Always Use `uv run` for Terminal Commands**: The PTY shell attached to AI agents does NOT have the virtual environment activated. All Python-related commands MUST be prefixed with `uv run` to ensure they execute within the correct environment.

    ```bash
    # ❌ Wrong - virtual environment not activated
    pytest
    python script.py
    ruff check

    # ✅ Correct - uses uv to run within the environment
    uv run pytest
    uv run python script.py
    uv run ruff check
    ```

3.  **Tool Priority Order**:
    - First: Use integrated tools (runTests, get_errors, read_file, etc.)
    - Second: Use `uv run` prefixed terminal commands when no tool is available
    - Avoid: Direct terminal commands without `uv run` for Python operations

4.  **NEVER Use Multiline Commands with Quotes**: The VS Code PTY shell will HANG and become unresponsive if you execute multiline commands using quotes (heredocs, multiline strings, etc.). This is a critical issue that breaks the terminal session.

    ```bash
    # ❌ FORBIDDEN - Will cause PTY shell to hang
    cat << 'EOF'
    some content
    EOF

    python -c "
    import sys
    print(sys.version)
    "

    # ✅ Correct - Use temporary files instead
    # 1. Create a temp file using create_file tool
    # 2. Execute: uv run python temp_script.py
    # 3. Delete the temp file
    ```

5.  **Avoid `cat` for File Operations**: Use the `create_file` or `replace_string_in_file` tools directly instead of `cat` or `echo` with redirections. These tools are more reliable and don't risk terminal issues.

6.  **Minimize Terminal Usage**: Terminal commands should be a last resort. Always prefer:
    - File tools (`read_file`, `create_file`, `replace_string_in_file`) for file operations
    - `runTests` for test execution
    - `get_errors` for error checking
    - Other integrated tools when available

7.  **Verify Commands Before Documentation**: Before documenting any terminal command, ALWAYS execute it first to confirm it works. Do not assume commands will work based on common patterns.

    ```bash
    # Before writing "uv run pytest" in docs:
    # 1. Actually run it in the terminal
    # 2. Check if it succeeds or fails
    # 3. Document accordingly
    ```

**Verification Checklist for Updates:**
- [ ] Verified file paths and directory structure.
- [ ] Verified class and function names (case-sensitive).
- [ ] Verified method signatures and arguments.
- [ ] Verified configuration environment variable prefixes (e.g., `spakky.plugins.rabbitmq__`).
- [ ] Verified import paths.
- [ ] **Tested all terminal commands** by executing them before documenting.
- [ ] **Updated all sub-package README.md files** with consistent information.
