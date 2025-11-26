# Spakky Framework - AI Coding Instructions

## Architecture Overview

Spakky is a Spring-inspired dependency injection framework for Python with AOP and plugin system:

- **Core (`spakky/`)**: DI/IoC container, AOP aspects, stereotypes, and application context
- **Plugins (`plugins/`)**: Framework extensions (FastAPI, RabbitMQ, Typer, Security)
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
    │   │   └── event/        # Event publisher/consumer
    │   └── src/tests/
    │
    ├── spakky-security/      # Security utilities
    │   ├── src/spakky_security/
    │   │   ├── cryptography/ # Encryption/decryption
    │   │   └── password/     # Password hashing
    │   └── src/tests/
    │
    └── spakky-typer/         # CLI integration
        ├── src/spakky_typer/
        │   ├── stereotypes/  # CliController stereotype
        │   └── utils/        # Asyncio utilities
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

- **`@Aspect()`** and **`@AsyncAspect()`**: Decorators for defining cross-cutting concerns
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
  - Used for route registration, middleware injection, etc.
  - Implements `post_process(self, pod: object) -> object` method
  - Can implement `ILoggerAware`, `IContainerAware` for framework services

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

### Post-Processors

Post-processors allow plugins to modify Pods after creation:

```python
from spakky.pod.interfaces.post_processor import IPostProcessor
from spakky.pod.annotations.pod import Pod
from spakky.pod.annotations.order import Order

@Order(0)
@Pod()
class RegisterRoutesPostProcessor(IPostProcessor, ILoggerAware, IContainerAware):
    def set_logger(self, logger: Logger) -> None:
        self.__logger = logger

    def set_container(self, container: IContainer) -> None:
        self.__container = container

    def post_process(self, pod: object) -> object:
        # Modify pod or register routes
        if ApiController.exists(pod):
            # Register routes from controller
            pass
        return pod
```

## Development Patterns

### Application Bootstrap

The application lifecycle follows a builder pattern:

```python
from spakky.application.application import SpakkyApplication
from spakky.application.application_context import ApplicationContext
import logging

# Setup logger
logger = logging.getLogger("app")

# Build and start application
app = (
    SpakkyApplication(ApplicationContext(logger))
    .load_plugins()                    # Load all plugins from entry points
    .enable_async_logging()            # Enable async logging aspects
    .scan(my_package)                  # Scan package for @Pod annotated classes
    .add(CustomPod)                    # Manually register specific Pods
    .start()                           # Initialize container and aspects
)

# Access container
user_service = app.container.get(UserService)
```

**Key methods**:

- `load_plugins()`: Discovers and loads all plugins via entry points
- `scan(module)`: Scans module for `@Pod`, `@Controller`, `@UseCase`, etc.
- `add(pod_type)`: Manually registers a Pod type
- `start()`: Finalizes container setup and runs post-processors

### FastAPI Controllers

Use `@ApiController(prefix)` with route decorators from `spakky_fastapi.routes`:

```python
from spakky_fastapi.stereotypes.api_controller import ApiController
from spakky_fastapi.routes import get, post, put, delete, patch, websocket
from spakky.aspects.logging import Logging
from fastapi import WebSocket
from pydantic import BaseModel

class CreateUserRequest(BaseModel):
    email: str
    username: str

@ApiController("/users", tags=["users"])
class UserController:
    def __init__(self, use_case: UserUseCase) -> None:
        self.use_case = use_case

    @Logging()
    @get("/{id}")
    async def get_user(self, id: int) -> User:
        """Get user by ID - response model inferred from return type"""
        return await self.use_case.get_user(id)

    @post("", description="Create a new user")
    async def create_user(self, request: CreateUserRequest) -> User:
        """Request body automatically parsed via Pydantic"""
        return await self.use_case.create_user(request.email, request.username)

    @websocket("/ws")
    async def websocket_endpoint(self, websocket: WebSocket) -> None:
        await websocket.accept()
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Echo: {data}")
```

**Available route decorators**: `get`, `post`, `put`, `delete`, `patch`, `head`, `options`, `websocket`

**Features**:

- Automatic response model inference from return type hints
- FastAPI dependency injection works alongside Spakky DI
- Route names auto-generated from method names (snake_case → Title Case)
- Support for all FastAPI response classes (`FileResponse`, `PlainTextResponse`, etc.)

### RabbitMQ Event Handlers

Use `@EventHandler` stereotype with `@on_event` decorators.

**Important**: Spakky enforces a 1:1 mapping between an event type and a handler method within a single `@EventHandler` class. Defining multiple handlers for the same event type in the same class will raise a `DuplicateEventHandlerError`.

**Message Validation**: If a message received from RabbitMQ is missing required metadata (`consumer_tag` or `delivery_tag`), an `InvalidMessageError` will be raised.

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

    @command("list")
    async def list_users(self) -> None:
        """List all users"""
        users = await self.user_service.list_all()
        for user in users:
            print(f"{user.id}: {user.username} ({user.email})")
```

**CLI usage**: `python main.py user create --email test@example.com --username testuser`

### Test Structure

Tests follow a consistent pattern across all packages:

- **Location**: `src/tests/` directory in each package (core and plugins)
- **Structure**: Mirror source structure for unit tests
- **Fixtures**: Define in `conftest.py` using `SpakkyApplication`
- **Test apps**: Create dummy applications in `src/tests/apps/` for integration tests

```python
# conftest.py
import pytest
from spakky.application.application import SpakkyApplication
from spakky.application.application_context import ApplicationContext

@pytest.fixture
def application() -> SpakkyApplication:
    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins()
        .scan(test_apps_module)
        .start()
    )
    return app

@pytest.fixture
def user_service(application: SpakkyApplication) -> UserService:
    return application.container.get(UserService)
```

**Testing FastAPI endpoints**:

```python
from fastapi.testclient import TestClient

def test_get_user(application: SpakkyApplication) -> None:
    fast_api = application.container.get(FastAPI)
    client = TestClient(fast_api)
    response = client.get("/users/1")
    assert response.status_code == 200
```

## Build & Test Commands

```bash
# Install all dependencies (including dev dependencies)
uv sync --all-extras

# Install all git hooks (pre-commit, commit-msg, pre-push)
uv run pre-commit install -t pre-commit -t commit-msg -t pre-push

# Run all tests with coverage (from root)
uv run pytest

# Run tests for specific plugin
cd plugins/spakky-fastapi
uv run pytest

# Run tests in parallel
uv run pytest -n auto

# Run with verbose output
uv run pytest -vv

# Generate coverage report
uv run pytest --cov --cov-report=html

# Format code
uv run ruff format

# Lint code
uv run ruff check

# Lint with auto-fix
uv run ruff check --fix

# Run pre-commit hooks manually
uv run pre-commit run --all-files

# Run pre-push hooks manually (tests)
uv run pre-commit run --all-files --hook-stage pre-push

# Type checking (if using pyrefly)
uv run pyrefly check
```

### Git Hook Workflow

The monorepo uses a two-stage hook system:

**On `git commit`:**
- Root hook runs `scripts/run_subproject_precommit.py`
- Only changed sub-projects are checked (lint, format, typecheck)
- Commitizen validates commit message format

**On `git push`:**
- Root hook runs `scripts/run_subproject_tests.py`
- Only changed sub-projects run pytest
- Prevents slow tests from blocking every commit

## File Conventions

- **Source code**: `src/{package_name}/` directory in each package
- **Tests**: `src/tests/` directory, mirroring source structure
- **Imports**: Use absolute imports (`from spakky.pod.annotations.pod import Pod`)
- **Type hints**: Required for all public APIs and constructor injection
- **Naming**:
  - Packages: `snake_case` (e.g., `spakky_fastapi`)
  - Classes: `PascalCase` (e.g., `UserController`)
  - Functions/methods: `snake_case` (e.g., `get_user`)
  - Constants: `UPPER_SNAKE_CASE`
  - **Protocols**: Must use `I` prefix (e.g., `IService`, `IContainer`, `IRepository`)
  - **Abstract Classes**: Must use `Abstract` prefix (e.g., `AbstractEntity`, `AbstractCommand`, `AbstractBackgroundService`)
- **Files**:
  - `__init__.py`: Package exports (use `__all__` for public API)
  - `py.typed`: Marker file for typed packages (present in all packages)
  - `pyproject.toml`: Package metadata, dependencies, and tool configuration

### Class Naming Conventions

**Protocol Classes (Interface definitions)**:
- Inherit from `Protocol` (with `@runtime_checkable` decorator)
- Always prefix class name with `I`
- Examples:
  ```python
  @runtime_checkable
  class IService(Protocol):
      @abstractmethod
      def start(self) -> None: ...

  @runtime_checkable
  class IUserRepository(Protocol):
      @abstractmethod
      def find_by_id(self, id: int) -> User | None: ...
  ```

**Abstract Classes (Base implementations)**:
- Inherit from `ABC`
- Always prefix class name with `Abstract`
- Examples:
  ```python
  class AbstractEntity(ABC):
      @abstractmethod
      def validate(self) -> None: ...

  class AbstractBackgroundService(IService, ABC):
      @abstractmethod
      def run(self) -> None: ...
  ```

**Concrete Classes**:
- No special prefix required
- Use descriptive `PascalCase` names
- Examples: `UserService`, `PostgresRepository`, `LoggingAspect`

## Critical Integration Points

### Plugin Registration

- Plugins **must** register via entry points in `pyproject.toml`
- Entry point group: `spakky.plugins`
- Entry point value: Points to `initialize` function
- Plugin loading happens during `load_plugins()` call

### Post-Processor Execution

- Post-processors modify Pods **after** instantiation but **before** use
- Order controlled via `@Order(n)` (lower numbers execute first)
- Common uses: Route registration, middleware injection, proxy wrapping
- Post-processors can access container and logger via aware interfaces

### Context Management

- `ApplicationContext` manages Pod lifecycle
- Context-scoped Pods use `ContextVar` for thread-safe request isolation
- **Context clearing happens at endpoint/handler entry points**, not in middleware:
  - **FastAPI**: `clear_context()` is called at the start of each route handler in `RegisterRoutesPostProcessor`
  - **RabbitMQ**: `clear_context()` is called at the start of each event handler in `RabbitMQPostProcessor`
  - **Typer**: `clear_context()` is called at the start of each CLI command in `TyperCLIPostProcessor`
- Async tasks inherit context automatically
- Clean up resources in `ApplicationContext` shutdown

### Dependency Resolution

- Constructor injection resolved via type hints (Python's `typing` module)
- Circular dependencies detected at runtime with clear error messages
- Use `@Primary` or qualifiers when multiple implementations exist
- Lazy loading supported for complex dependency graphs

## Common Pitfalls

### FastAPI Integration

- **DON'T** instantiate `FastAPI()` directly - it's automatically registered as a Pod
- **DO** retrieve FastAPI instance from container: `app.container.get(FastAPI)`
- **DON'T** mix FastAPI's native dependency injection with constructor injection
- **DO** use constructor injection for services, FastAPI DI for request-scoped data

### Async/Await Patterns

- **Controllers**: Use `async def` for I/O-bound operations
- **Aspects**: Use `@AsyncAspect` and `IAsyncAspect` for async methods
- **Aspects**: Use `@Aspect` and `IAspect` for sync methods
- **Mixing**: Don't call async methods without `await` or sync methods with `await`
- **Testing**: Use `pytest-asyncio` and `asyncio_mode = "auto"` in pytest config

### Plugin Initialization Order

1. `SpakkyApplication` created with `ApplicationContext`
2. `load_plugins()` discovers and runs plugin `initialize()` functions
3. `scan()` or `add()` registers Pods
4. `start()` creates container, resolves dependencies, runs post-processors

### Circular Dependencies

- **Detection**: Circular dependencies are detected at runtime during resolution
- **Workaround**: Use lazy loading, factory patterns, or redesign dependencies
- **Common cause**: A → B → A in constructor injection

### Type Hints and Injection

- **Required**: All injected dependencies must have type hints
- **Interfaces**: Prefer abstract classes or protocols for dependency types
- **Generic types**: Supported but need proper variance annotations

### Aspect Application

- Aspects apply to **methods**, not functions at module level
- Pointcut predicates should be lightweight (called frequently)
- Aspect order matters when multiple aspects match same method
- Proxy creation adds minimal overhead but affects identity checks (`is`)

## Debugging Tips

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("spakky")
logger.setLevel(logging.DEBUG)
```

### Inspect Container

```python
# List all registered Pods
for pod in app.container._pods:
    print(f"{pod.name}: {pod.type_}")

# Check if Pod is registered
from spakky.pod.annotations.pod import Pod
assert Pod.exists(MyClass)
```

### Common Error Messages

- `"Cannot determine scan path"`: Pass explicit module to `scan()`
- `"Circular dependency detected"`: Check constructor injection chain
- `"No Pod found for type X"`: Class not decorated with `@Pod` or not scanned
- `"Multiple Pods found for type X"`: Use qualifiers or `@Primary`
- `"Handler for event type 'X' is already registered"`: RabbitMQ plugin enforces 1:1 event-to-handler mapping
- `"Invalid message received from RabbitMQ"`: Message missing required `consumer_tag` or `delivery_tag`

## Testing Best Practices

### Test Organization

- **Mirror source structure**: Tests in `src/tests/` should mirror the structure of `src/{package}/`
- **File naming conflicts**: Avoid duplicate test file names across different packages (e.g., use `test_event_error.py`, `test_external_error.py` instead of multiple `test_error.py`)
- **Unique test apps**: Create dummy applications in `src/tests/apps/` for integration testing
- **Fixtures**: Define reusable fixtures in `conftest.py` at appropriate scope levels

### Unit Test Patterns

**Protocol and Interface Testing**:

```python
# Test that protocols exist and have required methods
def test_event_consumer_protocol() -> None:
    assert hasattr(IEventConsumer, "register")

# For runtime_checkable protocols, test isinstance
def test_protocol_implementation() -> None:
    class ConcreteImpl:
        def register(self, event, handler): ...

    assert isinstance(ConcreteImpl(), IEventConsumer)
```

**Abstract Class Testing**:

```python
# Test abstract classes by creating concrete implementations
def test_abstract_query() -> None:
    class TestQuery(AbstractQuery):
        pass

    query = TestQuery()
    assert isinstance(query, AbstractQuery)
```

**Error Case Coverage**:

```python
# Always test the negative path for isinstance checks
def test_not_equal_different_type() -> None:
    encoder = PasswordEncoder(password="test")
    assert encoder != "not_an_encoder"  # Covers isinstance False branch
    assert encoder != 123
```

**Magic Methods**:

```python
# Test all special methods for full coverage
def test_magic_methods() -> None:
    obj = MyClass(value="test")
    assert str(obj) == "expected_string"
    assert repr(obj) == str(obj)  # Often calls str()
    assert hash(obj) == hash("test")
    assert obj == MyClass(value="test")
    assert obj != MyClass(value="other")
```

### Aspect and AOP Testing

**Testing Aspect Errors**:

```python
# Aspects require proper inheritance and return types
@Aspect()
def bad_aspect() -> DummyClass:  # Need return type for function-based Pods
    return DummyClass()

# Test that AspectInheritanceError is raised
with pytest.raises(AspectInheritanceError):
    aspect.matches(target)
```

**Testing Aspect Pointcuts**:

```python
# Test that aspects match and execute correctly
@Aspect()
class LoggingAspect(IAspect):
    @Before(lambda x: Logging.exists(x))
    def before(self, *args, **kwargs) -> None:
        # Aspect logic
        pass

# Verify aspect is applied to annotated methods
assert aspect.matches(service.method)
```

### Middleware and Error Handling

**Testing Debug Mode**:

```python
# Test both debug and non-debug paths
def test_error_handling_debug() -> None:
    middleware = ErrorHandlingMiddleware(app, debug=True)
    # Trigger error and verify traceback is printed

def test_error_handling_no_debug() -> None:
    middleware = ErrorHandlingMiddleware(app, debug=False)
    # Trigger error and verify clean error response
```

**Testing Exception Paths**:

```python
# Use TestClient with raise_server_exceptions=False
with TestClient(app, raise_server_exceptions=False) as client:
    response = client.get("/error-endpoint")
    assert response.status_code == 500
```

### Dependency Injection Testing

**Testing Aware Interfaces**:

```python
# Test that post-processors correctly set dependencies
def test_container_aware() -> None:
    @Pod()
    class Service(IContainerAware):
        def __init__(self) -> None:
            self.container: object | None = None

        def set_container(self, container: object) -> None:
            self.container = container

    processor = ApplicationContextAwareProcessor(context, logger)
    service = Service()
    processed = processor.post_process(service)

    assert isinstance(processed, Service)
    assert processed.container is context
```

**Testing with Qualifiers**:

```python
# Test Pod resolution with name qualifiers
@Pod(name="service_a")
class ServiceA(IService): ...

@Pod(name="service_b")
class ServiceB(IService): ...

service_a = inject(context, type_=IService, name="service_a")
service_b = inject(context, type_=IService, name="service_b")
assert service_a != service_b
```

### Coverage Best Practices

**Target High Coverage**:

- Aim for 95%+ coverage on core framework code
- 100% coverage is achievable and recommended for plugins
- Remaining gaps are usually error handling edge cases or defensive programming

**Focus Areas**:

1. **Branch coverage**: Test both True and False paths of all conditions
2. **Type checking**: Test isinstance checks with wrong types
3. **Magic methods**: Test `__str__`, `__repr__`, `__eq__`, `__hash__`, etc.
4. **Protocol compliance**: Verify all required methods exist
5. **Error paths**: Test ValueError, TypeError, custom exceptions

**Tools**:

```bash
# Run tests with coverage report
uv run pytest --cov=package_name --cov-report=term-missing

# Generate HTML report for detailed analysis
uv run pytest --cov=package_name --cov-report=html

# Run specific test file
uv run pytest path/to/test_file.py -v

# Run with parallel execution
uv run pytest -n auto
```

### Common Test Pitfalls

**1. Import Path Mismatches**:

- Clear `__pycache__` if you get "import file mismatch" errors
- Use unique test file names across packages

**2. Type Annotations**:

- Function-based Pods need return type annotations
- Test fixtures should have proper type hints for IDE support

**3. Protocol Testing**:

- Use `hasattr()` for simple protocol validation
- Use `isinstance()` only with `@runtime_checkable` protocols

**4. Async Testing**:

- Use `pytest-asyncio` with `asyncio_mode = "auto"` in pytest config
- Don't mix sync and async test fixtures

**5. Fixture Scope**:

- Use `scope="function"` for tests that modify state
- Use `scope="package"` or `scope="session"` for expensive setup
- Clean up resources in fixture teardown

### Test-Driven Development Tips

**1. Write Tests First**: For new features, write failing tests before implementation
**2. Start Simple**: Begin with happy path, then add edge cases
**3. Test Interfaces**: Focus on testing behavior through interfaces, not implementation
**4. Mock Sparingly**: Prefer real objects in unit tests; use mocks for external dependencies
**5. Descriptive Names**: Test names should describe what they verify, not what they do

## Documentation Standards

### Docstring Style Guide

Spakky Framework follows **Google Style Python Docstrings** as specified in the Google Python Style Guide (https://google.github.io/styleguide/pyguide.html) and supported by Napoleon Sphinx extension (https://sphinxcontrib-napoleon.readthedocs.io/).

#### Module Docstrings

Every module should have a docstring describing its purpose:

```python
"""One-line summary of the module.

Optional longer description providing more context about what the module
contains and how it should be used. Can span multiple paragraphs if needed.
"""
```

#### Function and Method Docstrings

Functions and methods with type annotations should omit type information from Args section:

```python
def fetch_user(user_id: int, include_deleted: bool = False) -> User | None:
    """Fetch a user by ID from the database.

    Longer description if needed to explain the behavior in more detail.

    Args:
        user_id: The unique identifier for the user.
        include_deleted: Whether to include soft-deleted users in the search.

    Returns:
        The User object if found, None otherwise.

    Raises:
        DatabaseError: If there's a connection issue with the database.
        ValidationError: If user_id is invalid.
    """
```

**For functions without type annotations**, include types in Args:

```python
def legacy_function(param1, param2):
    """Legacy function without type hints.

    Args:
        param1 (int): The first parameter.
        param2 (str): The second parameter.

    Returns:
        bool: True if successful, False otherwise.
    """
```

#### Class Docstrings

Classes should document their purpose and public attributes:

```python
class UserService:
    """Service for managing user operations.

    This service handles all user-related business logic including
    authentication, authorization, and profile management.

    Attributes:
        repository: The repository for user data access.
        cache: Redis cache for user sessions.
    """

    repository: IUserRepository
    """Repository for accessing user data from the database."""

    cache: RedisCache
    """Cache instance for storing user session data."""

    def __init__(self, repository: IUserRepository, cache: RedisCache) -> None:
        """Initialize the user service.

        Args:
            repository: The repository for user data access.
            cache: Cache instance for sessions.
        """
        self.repository = repository
        self.cache = cache
```

#### Attribute Docstrings

Class and instance attributes should be documented using **attribute docstrings** (string literal immediately following the attribute):

```python
class Config:
    """Application configuration."""

    max_connections: int = 100
    """Maximum number of concurrent database connections."""

    timeout: float = 30.0
    """Request timeout in seconds."""

    def __init__(self, debug: bool = False) -> None:
        """Initialize configuration.

        Args:
            debug: Enable debug mode.
        """
        self.debug = debug
        """Whether debug mode is enabled."""
```

#### Special Sections

- **Args**: Document parameters (omit types if type-annotated)
- **Returns**: Describe the return value and its meaning
- **Yields**: For generators instead of Returns
- **Raises**: List exceptions that are part of the API contract
- **Example** or **Examples**: Show usage examples
- **Note**: Important information or caveats
- **Warning**: Critical warnings about usage
- **See Also**: References to related functionality

#### What NOT to Document

1. **Test files**: Test code doesn't need docstrings unless complex setup is required
2. **Private internals**: Implementation details not part of the public API
3. **Self-evident code**: Don't restate what's obvious from the code
4. **@override methods**: Use `@override` decorator instead of repeating parent docstring
5. **Simple private methods**: Trivial helpers like `__set_cache()`, `__get_cache()` where behavior is obvious from the name

#### Private Method Guidelines

Since this framework is intended for external use, apply different standards for private vs public methods:

**Public API (always document)**:
- All public methods, functions, and classes
- Protocol/interface methods
- Properties exposed to users

**Private methods (document selectively)**:
- ✅ **Document**: Complex logic, recursive algorithms, non-obvious behavior
  - Example: `__get_dependencies()` - complex parameter analysis
  - Example: `__instantiate_pod()` - recursive dependency resolution
  - Example: `__resolve_candidate()` - multi-step matching logic

- ❌ **Skip**: Simple helpers, obvious getters/setters, trivial wrappers
  - Example: `__set_singleton_cache()` - just sets dict value
  - Example: `__get_singleton_cache()` - just gets dict value
  - Example: `__add_post_processor()` - just appends to list

**Rule of thumb**: If the method name and signature clearly convey what it does, skip the docstring for private methods.

#### Docstring Templates

**Simple function**:
```python
def simple_function(arg: str) -> bool:
    """One-line description ending with period."""
    return True
```

**Complex function**:
```python
def complex_function(
    required_arg: str,
    optional_arg: int = 0,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """Short summary line.

    Detailed explanation of what the function does, including any
    important behavioral details or side effects.

    Args:
        required_arg: Description of required argument.
        optional_arg: Description with default value explained.
        *args: Variable positional arguments.
        **kwargs: Variable keyword arguments.

    Returns:
        A dictionary mapping keys to values with detailed explanation
        of the structure and contents.

    Raises:
        ValueError: When input validation fails.
        RuntimeError: When operation cannot be completed.

    Example:
        >>> result = complex_function("test", optional_arg=5)
        >>> print(result["status"])
        success
    """
```

### CI/CD Architecture

The project uses GitHub Actions with a split workflow architecture for parallel execution and faster feedback:

- **`ci.yml`**: Core framework tests and linting
- **`ci-fastapi.yml`**: FastAPI plugin tests
- **`ci-rabbitmq.yml`**: RabbitMQ plugin tests
- **`ci-security.yml`**: Security plugin tests
- **`ci-typer.yml`**: Typer plugin tests
- **`release.yml`**: Automated deployment to PyPI on tag push

Each workflow runs independently, ensuring that changes in one plugin do not block or fail the build for others.

### PyPI Package Structure

**Core Package**: `spakky`
- Standalone framework with no runtime dependencies
- Provides optional-dependencies (extras) for plugin installation
- Users can install: `pip install spakky[fastapi,rabbitmq]`

**Plugin Packages**: Independent PyPI packages
- `spakky-fastapi`: FastAPI integration (depends on `spakky>=0.1.0`)
- `spakky-rabbitmq`: RabbitMQ event system (depends on `spakky>=0.1.0`)
- `spakky-security`: Security utilities (depends on `spakky>=0.1.0`)
- `spakky-typer`: CLI integration (depends on `spakky>=0.1.0`)

### Installation Methods

```bash
# Core only
pip install spakky

# With specific plugins (via extras)
pip install spakky[fastapi]
pip install spakky[fastapi,rabbitmq]
pip install spakky[all]

# Standalone plugin installation
pip install spakky-fastapi
```

### Version Management

**Tool**: commitizen 4.10.0+ with Conventional Commits

**Commands**:
```bash
# Bump version automatically
uv run cz bump

# Create version tag
git push --tags  # Triggers GitHub Actions release workflow
```

**Version Files**: Automatically updated by commitizen
- `spakky/pyproject.toml`
- `plugins/spakky-fastapi/pyproject.toml`
- `plugins/spakky-rabbitmq/pyproject.toml`
- `plugins/spakky-security/pyproject.toml`
- `plugins/spakky-typer/pyproject.toml`

### Automated Deployment

**GitHub Actions Workflow**: `.github/workflows/release.yml`

**Trigger**: Git tag push (`git push --tags`)

**Change Detection Logic**:
- `spakky/` changes → Deploy spakky only
- `plugins/spakky-fastapi/` changes → Deploy spakky-fastapi only
- `plugins/spakky-rabbitmq/` changes → Deploy spakky-rabbitmq only
- `plugins/spakky-security/` changes → Deploy spakky-security only
- `plugins/spakky-typer/` changes → Deploy spakky-typer only
- First release (no previous tag) → Deploy all packages

**Requirements**:
- GitHub Secret: `PYPI_API_TOKEN` (PyPI API token)
- Permissions: `contents: write`, `id-token: write`

**Process**:
1. Detect changed packages (git diff vs previous tag)
2. Build changed packages (`uv build --package <name>`)
3. Publish to PyPI (`uv publish --token $UV_PUBLISH_TOKEN`)
4. Create GitHub Release (auto-generated notes)

### Manual Deployment

```bash
# Build specific package
uv build --package spakky
uv build --package spakky-fastapi

# Publish to PyPI
export UV_PUBLISH_TOKEN="pypi-..."
uv publish --token $UV_PUBLISH_TOKEN
```

### Build Verification

All packages successfully build and generate wheel + sdist:
- spakky-0.1.0: 65KB wheel, 36KB tar.gz
- spakky_fastapi-0.1.0: 23KB wheel, 8.7KB tar.gz
- spakky_rabbitmq-0.1.0: 8.8KB wheel, 5.9KB tar.gz
- spakky_security-0.1.0: 20KB wheel, 11KB tar.gz
- spakky_typer-0.1.0: 7.3KB wheel, 4.7KB tar.gz

### Package Metadata

All packages include:
- **keywords**: Specific to package functionality
- **classifiers**: Development status, Python versions, licenses
- **[project.urls]**: Homepage, Repository, Documentation, Issues
- **dependencies**: Proper version constraints (e.g., `spakky>=0.1.0`)

**Core extras configuration** (spakky/pyproject.toml):
```toml
[project.optional-dependencies]
fastapi = ["spakky-fastapi>=0.1.0"]
rabbitmq = ["spakky-rabbitmq>=0.1.0"]
security = ["spakky-security>=0.1.0"]
typer = ["spakky-typer>=0.1.0"]
all = [
    "spakky-fastapi>=0.1.0",
    "spakky-rabbitmq>=0.1.0",
    "spakky-security>=0.1.0",
    "spakky-typer>=0.1.0",
]
```

### Conventional Commits for Deployment

**Format**: `<type>(<scope>): <subject>`

**Types**:
- `feat`: New feature (bumps MINOR version)
- `fix`: Bug fix (bumps PATCH version)
- `feat!` or `BREAKING CHANGE:`: Breaking change (bumps MAJOR version)
- `docs`, `style`, `refactor`, `test`, `chore`: No version bump

**Scopes**: `core`, `fastapi`, `rabbitmq`, `security`, `typer`

**Examples**:
```bash
git commit -m "feat(fastapi): add new middleware"
git commit -m "fix(rabbitmq): resolve duplicate handler issue"
git commit -m "feat(core)!: change Pod interface

BREAKING CHANGE: Pod.register() signature changed"
```

### Deployment Checklist

**Before First Release**:
1. ✅ Package metadata configured (all pyproject.toml files)
2. ✅ GitHub Actions workflow created (.github/workflows/release.yml)
3. ✅ commitizen configured (pyproject.toml)
4. ✅ Build verification passed (all packages build successfully)
5. ⏳ PyPI token created and added to GitHub Secrets

**Release Process**:
1. Commit changes with Conventional Commits format
2. Run `uv run cz bump` to update versions and create tag
3. Push tag: `git push --tags`
4. GitHub Actions automatically deploys changed packages
5. Verify on PyPI and test installation

**Post-Deployment Verification**:
```bash
# Test installation
pip install spakky[all]==0.1.0

# Test import
python -c "from spakky.application.application import SpakkyApplication"
```

### Troubleshooting

**Build fails**:
- Clear cache: `uv cache clean`
- Resync: `uv sync --all-extras`
- Check pyproject.toml syntax

**PyPI upload fails**:
- Verify `PYPI_API_TOKEN` in GitHub Secrets
- Check if version already exists on PyPI
- Verify token scope/permissions

**GitHub Actions fails**:
- Check workflow logs in Actions tab
- Verify repository permissions (Settings → Actions → General)
- Ensure `PYPI_API_TOKEN` secret is set

### Important Notes

- **DO NOT create separate MD files for documentation** - All information goes in this copilot-instructions.md
- **Monorepo structure**: Multiple packages in one repository
- **Independent versioning**: Each package maintains its own version
- **Workspace dependencies**: Local dev uses `{ workspace = true }`, PyPI uses version constraints
- **Entry points**: Plugins register via `[project.entry-points."spakky.plugins"]`
