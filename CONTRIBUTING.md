# Contributing to Spakky Framework

First off, thanks for taking the time to contribute! 🎉

The following is a set of guidelines for contributing to Spakky Framework and its plugins. These are mostly guidelines, not rules. Use your best judgment, and feel free to propose changes to this document in a pull request.

## 🛠 Development Setup

This project uses [`uv`](https://github.com/astral-sh/uv) for dependency management and workspace handling.

### Prerequisites

- Python 3.11 or higher
- `uv` installed

### Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/E5presso/spakky-framework.git
   cd spakky-framework
   ```

2. **Sync dependencies**

   This will install all dependencies for the core framework and all plugins, including development tools.

   ```bash
   uv sync --all-packages --all-extras
   ```

   > **💡 Understanding `uv sync` options:**
   >
   > | Command                               | When to use               | Description                                                                                                                                    |
   > | ------------------------------------- | ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
   > | `uv sync --all-packages --all-extras` | **Root directory**        | Installs all workspace packages and their optional dependencies. Use this when developing across multiple packages.                            |
   > | `uv sync --all-extras`                | **Sub-package directory** | Installs only the current package and its optional dependencies. Use this when working on a single plugin (e.g., `cd plugins/spakky-fastapi`). |
   >
   > The `--all-packages` flag is only needed at the workspace root to include all monorepo packages. When you `cd` into a sub-package, that package becomes the context, so `--all-extras` alone is sufficient.

### Opening Sub-Projects Independently

Each sub-project can be opened independently in VS Code while still using the root virtual environment:

1. **VS Code Settings**: Each sub-project has `.vscode/settings.json` with `python.defaultInterpreterPath` pointing to the root's `.venv`:

   ```json
   {
   	"python.defaultInterpreterPath": "${workspaceFolder}/../../.venv/bin/python"
   }
   ```

2. **Pre-commit Hooks**: All hooks use conditional path handling to work both from monorepo root and standalone.

3. **Terminal**: When opening a sub-project standalone, use `uv run` which automatically finds the correct virtual environment.

## 🧪 Running Tests

We use `pytest` for testing.

```bash
cd core/spakky
uv run pytest

cd plugins/spakky-fastapi
uv run pytest

# Run with coverage (from package directory)
uv run pytest --cov --cov-report=html
```

## 🎨 Coding Standards

### Pre-commit Hooks

We use **pre-commit** to enforce code quality checks.

- **On commit**: Linting, formatting, type checking (fast)
- **On push**: Unit tests for changed packages only (slower, but necessary)

```bash
# Install all hooks (pre-commit, commit-msg, and pre-push)
uv run pre-commit install -t pre-commit -t commit-msg -t pre-push

# Run pre-commit hooks manually
uv run pre-commit run --all-files

# Run pre-push hooks manually (includes pytest)
uv run pre-commit run --all-files --hook-stage pre-push
```

#### Hook Workflow

```
git commit
├── Root: monorepo-pre-commit
│   └── For each changed sub-project:
│       ├── trailing-whitespace
│       ├── check-yaml, check-json
│       ├── ruff (lint + format)
│       └── pyrefly (type check)
└── Root: commitizen (validate commit message)

git push
└── Root: monorepo-pre-push-tests
    └── For each changed sub-project:
        └── pre-commit --hook-stage pre-push
            └── pytest (unit tests)
```

Each sub-project's `.pre-commit-config.yaml` uses **conditional path handling** to work both from monorepo root and standalone:

```yaml
# Works from root: cd core/spakky && run
# Works standalone: run in current directory
entry: bash -c 'if [ -d "core/spakky" ]; then cd core/spakky; fi && uv run pyrefly check'
```

Our pre-commit configuration includes:

- **Monorepo hook**: Runs sub-project specific checks on changed files
- **Commitizen**: Validates commit messages follow Conventional Commits format

### Style Guide

We use **Ruff** for linting and formatting.

```bash
# Format code
uv run ruff format

# Lint code
uv run ruff check --fix
```

### Type Hinting

Spakky is a strictly typed framework. All public APIs and dependency injection points must have type hints.

- Use `typing` module features (e.g., `Protocol`, `TypeVar`, `cast`).
- We use `pyrefly` (or compatible type checkers) for validation.

#### `Any` Type Usage

**The use of `Any` type should be avoided whenever possible.** Use alternatives first:

- Use `TypeVar` for generic functions instead of `Any` return types.
- Use `object` as an upper bound when the type is truly unknown.
- Use `Protocol` to define structural typing contracts.
- Use `Union` or `|` for multiple known types.

**Allowed exceptions** (must be documented with an inline comment explaining why):

- External library interfaces with invariant generics (e.g., SQLAlchemy `Column[Any]`, `TypeEngine[Any]`).
- JSON parsing/serialization where the structure is truly dynamic.
- Decorator implementations that must preserve arbitrary signatures.

```python
# BAD: Using Any without justification
from typing import Any

def get_constraint(constraint_type: type) -> Any | None:
    ...

# GOOD: Using TypeVar
from typing import TypeVar

_T = TypeVar("_T")

def get_constraint(constraint_type: type[_T]) -> _T | None:
    ...

# GOOD: Any with justification (external library invariant generic)
def create_column() -> Column[Any]:  # Any: SQLAlchemy Column is invariant
    ...
```

#### `type: ignore` Comments

**The use of `# type: ignore` comments is prohibited.** Always find a proper type-safe solution or use `Any` with documentation if unavoidable.

### Logging Pattern

Spakky uses **standard Python logging** instead of dependency injection for loggers.

```python
from logging import getLogger

logger = getLogger(__name__)

@Pod()
class MyService:
    def do_something(self) -> None:
        logger.info("Doing something")
```

**Key points**:

- Declare a module-level `logger` using `getLogger(__name__)`
- Do NOT inject loggers via constructor or `ILoggerAware` (removed)
- `ApplicationContext` no longer accepts a `logger` parameter

### Naming Conventions

- **Packages**: `snake_case` (e.g., `spakky.plugins.fastapi`)
- **Classes**: `PascalCase` (e.g., `UserController`)
- **Functions/Methods**: `snake_case` (e.g., `get_user`)
- **Protocols (Interfaces)**: Must start with `I` (e.g., `IEventPublisher`, `IContainer`).
- **Abstract Classes**: Must start with `Abstract` (e.g., `AbstractEntity`, `AbstractEvent`, `AbstractDomainEvent`, `AbstractIntegrationEvent`).
- **Error Classes**: Must end with `Error` (e.g., `CannotDeterminePodTypeError`).
- **Async Classes**: Must start with `Async` (e.g., `AsyncTransactionalAspect`, `AsyncRabbitMQEventTransport`).

#### Inherited Type Suffix

Concrete classes must include the **inherited class/interface role as a suffix**.

| Inherited Type | Suffix | Example |
|---------------|--------|--------|
| `IAsyncAspect` | `~Aspect` | `AsyncTransactionalAspect` |
| `AbstractAsyncBackgroundService` | `~BackgroundService` | `AsyncOutboxRelayBackgroundService` |
| `IPostProcessor` | `~PostProcessor` | `RegisterRoutesPostProcessor` |
| `AbstractAsyncTransaction` | `~Transaction` | `AsyncTransaction` |

**Exception — Domain Models**: Domain models are exempt from the suffix rule. Use ubiquitous language (domain terminology) as-is.

```python
# ✅ Domain models: no suffix, use domain terms
class User(AbstractAggregateRoot[UUID]): ...
class OrderPlaced(AbstractDomainEvent): ...  # past participle
class Money(AbstractValueObject): ...

# ✅ Infrastructure/Framework: suffix required
class AsyncTransactionalAspect(IAsyncAspect): ...
class AsyncOutboxRelayBackgroundService(AbstractAsyncBackgroundService): ...
```

#### Domain Event Naming

- **DomainEvent**: Use **past participle only**. Do NOT append `DomainEvent` suffix.
  - `OrderPlaced` ✅ / `OrderPlacedDomainEvent` ❌
  - `UserCreated` ✅ / `UserCreatedEvent` ❌
- **IntegrationEvent**: Append `IntegrationEvent` suffix.
  - `OrderConfirmedIntegrationEvent` ✅

#### Generic Type Narrowing

When inheriting a Generic interface with concrete type parameters, **replace the Generic name with the narrowed type name**.

```python
# ✅ Generic narrowed → replace with type name
class UserRepository(IAsyncGenericRepository[User, UUID]): ...
class OrderRepository(IGenericRepository[Order, UUID]): ...

# ❌ Keeping Generic name
class UserGenericRepository(IAsyncGenericRepository[User, UUID]): ...
```

### Magic Numbers

**Avoid magic numbers.** Use named constants with descriptive names and docstrings.

```python
# BAD: Magic number
return String(length=255)

# GOOD: Named constant with documentation
DEFAULT_STRING_LENGTH: int = 255
"""Default length for fallback String column type."""

return String(length=DEFAULT_STRING_LENGTH)
```

**Allowed exceptions** (no constant needed):

- `0`, `1`, `-1` in obvious contexts (e.g., `range(0, n)`, `index + 1`).
- Common values like `100` for percentage calculations when context is clear.

### Error Class Guidelines

All framework errors inherit from `AbstractSpakkyFrameworkError`.

**For simple errors** (no additional context needed):

```python
class CannotUseOptionalReturnTypeInPodError(PodAnnotationFailedError):
    """Raised when function Pod has Optional return type."""

    message = "Cannot use optional return type in pod"
```

**For structured errors** (context data needed for programmatic access):

Override `__init__` to store structured data. **Do NOT override `__str__`** — detailed messages belong in logs, not errors:

```python
class CircularDependencyGraphDetectedError(AbstractSpakkyPodError):
    """Raised when circular dependency is detected."""

    message = "Circular dependency graph detected"

    def __init__(self, dependency_chain: list[type]) -> None:
        super().__init__()
        self.dependency_chain = dependency_chain

# Logging (where detailed messages belong):
except CircularDependencyGraphDetectedError as e:
    logger.error(
        "Circular dependency detected: %s",
        " -> ".join(t.__name__ for t in e.dependency_chain),
    )
```

**Guidelines**:

- **Errors are structured data, not descriptive text** — logs handle details
- **Do NOT use f-strings** to build descriptive error messages
- **Do NOT override `__str__`** — use the class `message` attribute
- Always call `super().__init__()` in custom `__init__`
- Keep `message` class attribute for basic error identification

**Key rules**:

- Simple errors: `message` class attribute only
- Structured errors: `__init__` for data, no `__str__` override

### Documentation

We follow the **Google Python Style Guide** for docstrings.

```python
def fetch_user(user_id: int) -> User | None:
    """Fetch a user by ID.

    Args:
        user_id: The unique identifier.

    Returns:
        The User object if found, None otherwise.
    """
```

## 🔌 Plugin Development

Spakky uses a formal plugin architecture. If you are contributing a new plugin:

1.  **Create Package**: Use `uv init` to create a new package in the workspace.

    ```bash
    # From workspace root
    cd plugins
    uv init --lib spakky-<name>
    cd spakky-<name>

    # Create proper package structure
    mkdir -p src/spakky/plugins/<name>
    touch src/spakky/plugins/<name>/__init__.py
    touch src/spakky/plugins/<name>/main.py
    ```

2.  **Register in Workspace**: Add the new package to root `pyproject.toml`'s `[tool.uv.workspace]` members.

    ```toml
    [tool.uv.workspace]
    members = [
      # ... existing packages ...
      "plugins/spakky-<name>",
    ]
    ```

3.  **Entry Point**: Define the entry point in the plugin's `pyproject.toml`.

    ```toml
    [project.entry-points."spakky.plugins"]
    spakky-<name> = "spakky.plugins.<name>.main:initialize"
    ```

4.  **Initialization**: Implement the `initialize` function in `main.py`.

    ```python
    from spakky.core.application.application import SpakkyApplication

    def initialize(app: SpakkyApplication) -> None:
        """Register your Pods and Post-Processors here."""
        pass
    ```

5.  **Version Synchronization**: Add the new package to root `pyproject.toml`'s `[tool.commitizen]` version_files list.

    ```toml
    [tool.commitizen]
    version_files = [
      # ... existing packages ...
      "plugins/spakky-<name>/pyproject.toml:version",
    ]
    ```

6.  **Package Registration**: All workspace packages are automatically detected from root `pyproject.toml`'s `[tool.uv.workspace]` members. No manual registration needed in scripts.

## 📦 Commit Messages

We use **Conventional Commits** to automate versioning and changelogs.

Format: `<type>(<scope>): <subject>`

- **Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
- **Scopes**: `core`, `domain`, `data`, `event`, `fastapi`, `kafka`, `rabbitmq`, `security`, `sqlalchemy`, `typer`, `outbox`, `outbox-sqlalchemy`

Examples:

- `feat(core): add new scope type`
- `fix(fastapi): resolve routing issue`
- `docs: update contributing guide`

## 🏷️ Versioning

We use **Semantic Versioning** with **unified single version** across all packages.

### Unified Version Strategy

All packages in the monorepo share the same version number. When any package changes, all packages are released together.

| Component        | Format       | Example                                        |
| ---------------- | ------------ | ---------------------------------------------- |
| **Tag**          | `v{version}` | `v3.3.0`                                       |
| **All packages** | Same version | `spakky==3.3.0`, `spakky-fastapi==3.3.0`, etc. |

### Bump Type Rules

| Commit Type                    | Bump  | Version Change    |
| ------------------------------ | ----- | ----------------- |
| `fix:`                         | Patch | `3.2.0` → `3.2.1` |
| `feat:`                        | Minor | `3.2.0` → `3.3.0` |
| `feat!:` or `BREAKING CHANGE:` | Major | `3.2.0` → `4.0.0` |

## 🚀 Pull Request Process

1.  Fork the repo and create your branch from `develop`.
2.  If you've added code that should be tested, add tests.
3.  Ensure the test suite passes. The CI system will automatically detect changed packages and run tests only for them.
4.  Make sure your code lints.
5.  Issue that pull request!

---

Happy coding! 🚀
