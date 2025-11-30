# Spakky Framework - AI Coding Instructions

## Architecture Overview

Spakky is a Spring-inspired dependency injection framework for Python with AOP and plugin system:

- **Core (`spakky/`)**: DI/IoC container, AOP aspects, stereotypes, and application context
- **Plugins (`plugins/`)**: Framework extensions (FastAPI, RabbitMQ, Typer, Security, Kafka)
- **Monorepo structure**: Uses `uv` workspace with shared tooling and cross-package dependencies
- **Python version**: Requires Python 3.11+
- **Build system**: Uses `uv` for dependency management and `uv_build` for packaging

## Project Structure

```
spakky-framework/
├── spakky/                    # Core framework package
│   ├── src/spakky/           # Core implementation
│   │   ├── aop/              # Aspect-Oriented Programming
│   │   ├── application/      # Application context and lifecycle
│   │   ├── aspects/          # Built-in aspects (Logging, Transactional)
│   │   ├── core/             # Core utilities (proxy, annotation, types)
│   │   ├── domain/           # Domain interfaces and abstractions
│   │   ├── pod/              # Dependency injection container
│   │   ├── service/          # Service layer components
│   │   ├── stereotype/       # Stereotype annotations
│   │   └── utils/            # Utility functions
│   └── src/tests/            # Core framework tests
│
└── plugins/
    ├── spakky-fastapi/       # FastAPI integration
    │   ├── src/spakky_fastapi/
    │   │   ├── middlewares/  # FastAPI middleware
    │   │   ├── post_processors/ # Route registration post-processors
    │   │   ├── routes/       # Route decorators (get, post, etc.)
    │   │   └── stereotypes/  # ApiController stereotype
    │   └── src/tests/        # Plugin tests
    │
    ├── spakky-rabbitmq/      # RabbitMQ event system
    │   ├── src/spakky_rabbitmq/
    │   │   ├── common/       # Configuration and constants
    │   │   └── event/        # Event publisher/consumer
    │   └── src/tests/
    │
    ├── spakky-security/      # Security utilities
    │   ├── src/spakky_security/
    │   │   ├── cryptography/ # Encryption/decryption
    │   │   └── password/     # Password hashing
    │   └── src/tests/
    │
    ├── spakky-typer/         # CLI integration
    │   ├── src/spakky_typer/
    │   │   ├── stereotypes/  # CliController stereotype
    │   │   └── utils/        # Asyncio utilities
    │   └── src/tests/
    │
    └── spakky-kafka/         # Apache Kafka event system
        ├── src/spakky_kafka/
        │   ├── common/       # Configuration and constants
        │   └── event/        # Event publisher/consumer
        └── src/tests/
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
from spakky.pod.annotations.pod import Pod

@Pod(name="user_service", scope=Pod.Scope.SINGLETON)
class UserService:
    def __init__(self, repository: IUserRepository) -> None:
        self.repository = repository
```

### Stereotypes

Stereotypes extend `@Pod` with semantic meaning and additional behaviors:

- **`@Controller`**: Base stereotype for grouping related handlers (from `spakky.stereotype.controller`)
- **`@UseCase`**: Encapsulates business logic (from `spakky.stereotype.usecase`)
- **`@ApiController(prefix)`**: FastAPI REST controllers with route registration (from `spakky_fastapi.stereotypes`)
- **`@CliController(group_name)`**: Typer CLI controllers (from `spakky_typer.stereotypes`)
- **`@EventHandler`**: Event handlers for RabbitMQ/Kafka (from `spakky.stereotype.event_handler`)

All stereotypes are automatically registered as Pods and support dependency injection.

```python
from spakky_fastapi.stereotypes.api_controller import ApiController
from spakky_fastapi.routes import get, post

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
  - `@Logging()`: Automatic logging of method calls (from `spakky.aspects.logging`)
  - `@Transactional()`: Database transaction management (from `spakky.aspects.transactional`)
- **Order control**: Use `@Order(n)` to control aspect execution order

```python
from spakky.aop.aspect import AsyncAspect
from spakky.aop.interfaces.aspect import IAsyncAspect
from spakky.aop.pointcut import Around
from spakky.pod.annotations.order import Order

@Order(0)
@AsyncAspect()
class LoggingAspect(IAsyncAspect):
    @Around(lambda x: Logging.exists(x) and iscoroutinefunction(x))
    async def around_async(self, joinpoint: AsyncFunc, *args, **kwargs) -> Any:
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
spakky-fastapi = "spakky_fastapi.main:initialize"
```

```python
# In spakky_fastapi/main.py
from spakky.application.application import SpakkyApplication

def initialize(app: SpakkyApplication) -> None:
    """Plugin initialization function"""
    # Register plugin-specific Pods, post-processors, etc.
    pass
```

## Development Patterns

### Application Bootstrap

The application lifecycle follows a builder pattern:

```python
from spakky.application.application import SpakkyApplication
from spakky.application.application_context import ApplicationContext
from spakky.aspects import AsyncLoggingAspect, LoggingAspect

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

**Configuration**: Set environment variables with the `SPAKKY_RABBITMQ__` prefix (note the double underscore at the end):

```bash
export SPAKKY_RABBITMQ__USE_SSL="false"
export SPAKKY_RABBITMQ__HOST="localhost"
export SPAKKY_RABBITMQ__PORT="5672"
export SPAKKY_RABBITMQ__USER="guest"
export SPAKKY_RABBITMQ__PASSWORD="guest"
export SPAKKY_RABBITMQ__EXCHANGE_NAME="my-exchange"
```

**Event Consuming**: Use `@EventHandler` stereotype with `@on_event` decorators.

```python
from spakky.stereotype.event_handler import EventHandler, on_event
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
from spakky_typer.stereotypes.cli_controller import CliController, command

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

### Running Tests

**IMPORTANT**: This monorepo does NOT support running tests from the root directory. Each package manages its own tests independently.

```bash
# ❌ Wrong - This will FAIL with import errors
cd /path/to/spakky-framework
uv run pytest

# ✅ Correct - Run tests from each package directory
cd spakky
uv run pytest

cd plugins/spakky-fastapi
uv run pytest

cd plugins/spakky-rabbitmq
uv run pytest

# etc. for each package
```

**Available packages for testing**:
- `spakky/` - Core framework
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
- [ ] Verified configuration environment variable prefixes (e.g., `SPAKKY_RABBITMQ__`).
- [ ] Verified import paths.
- [ ] **Tested all terminal commands** by executing them before documenting.
