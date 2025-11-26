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
   > | Command | When to use | Description |
   > |---------|-------------|-------------|
   > | `uv sync --all-packages --all-extras` | **Root directory** | Installs all workspace packages and their optional dependencies. Use this when developing across multiple packages. |
   > | `uv sync --all-extras` | **Sub-package directory** | Installs only the current package and its optional dependencies. Use this when working on a single plugin (e.g., `cd plugins/spakky-fastapi`). |
   >
   > The `--all-packages` flag is only needed at the workspace root to include all monorepo packages. When you `cd` into a sub-package, that package becomes the context, so `--all-extras` alone is sufficient.

## 🧪 Running Tests

We use `pytest` for testing.

```bash
# Run all tests
uv run pytest

# Run tests for a specific package
uv run pytest plugins/spakky-fastapi

# Run with coverage
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

# Run pre-push hooks manually
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
        └── pytest (unit tests)
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

- Use `typing` module features (e.g., `Protocol`, `Any`, `cast`).
- We use `pyrefly` (or compatible type checkers) for validation.

### Naming Conventions

- **Packages**: `snake_case` (e.g., `spakky_fastapi`)
- **Classes**: `PascalCase` (e.g., `UserController`)
- **Functions/Methods**: `snake_case` (e.g., `get_user`)
- **Protocols (Interfaces)**: Must start with `I` (e.g., `IService`, `IContainer`).
- **Abstract Classes**: Must start with `Abstract` (e.g., `AbstractEntity`).
- **Error Classes**: Must end with `Error` (e.g., `CannotDeterminePodTypeError`).

### Error Class Guidelines

All framework errors inherit from `AbstractSpakkyFrameworkError`. When creating custom errors:

**For fixed messages** (no context needed):

```python
class CannotUseOptionalReturnTypeInPodError(PodAnnotationFailedError):
    """Raised when function Pod has Optional return type."""
    message = "Cannot use optional return type in pod"
```

**For context-specific messages** (include details):

```python
class CannotDeterminePodTypeError(PodAnnotationFailedError):
    """Raised when Pod type cannot be inferred."""

    def __init__(self, target: PodType, param_name: str | type) -> None:
        super().__init__(
            f"Cannot determine pod type for '{target.__name__}' "
            f"(parameter: {param_name})"
        )
        self.target = target
        self.param_name = param_name
```

**Key rules**:
- Always call `super().__init__(message)` for proper `str(error)` support
- Store context as instance attributes for programmatic access
- Use descriptive f-string messages with the problematic values

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

1.  **Structure**: Create a new directory in `plugins/spakky-<name>`.
2.  **Entry Point**: Define the entry point in `pyproject.toml`.

    ```toml
    [project.entry-points."spakky.plugins"]
    spakky-name = "spakky_name.main:initialize"
    ```

3.  **Initialization**: Implement the `initialize` function.

    ```python
    from spakky.application.application import SpakkyApplication

    def initialize(app: SpakkyApplication) -> None:
        """Register your Pods and Post-Processors here."""
        pass
    ```

## 📦 Commit Messages

We use **Conventional Commits** to automate versioning and changelogs.

Format: `<type>(<scope>): <subject>`

- **Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
- **Scopes**: `core`, `fastapi`, `rabbitmq`, `security`, `typer`

Examples:

- `feat(core): add new scope type`
- `fix(fastapi): resolve routing issue`
- `docs: update contributing guide`

## 🏷️ Versioning

We use **Semantic Versioning** with **unified single version** across all packages.

### Unified Version Strategy

All packages in the monorepo share the same version number. When any package changes, all packages are released together.

| Component | Format | Example |
|-----------|--------|---------|
| **Tag** | `v{version}` | `v3.3.0` |
| **All packages** | Same version | `spakky==3.3.0`, `spakky-fastapi==3.3.0`, etc. |

### Bump Type Rules

| Commit Type | Bump | Version Change |
|-------------|------|----------------|
| `fix:` | Patch | `3.2.0` → `3.2.1` |
| `feat:` | Minor | `3.2.0` → `3.3.0` |
| `feat!:` or `BREAKING CHANGE:` | Major | `3.2.0` → `4.0.0` |

### Version Bump Commands

```bash
# Preview next version (dry-run)
uv run python scripts/bump_packages.py --dry-run

# Bump version, create commit and tag
uv run python scripts/bump_packages.py

# Push changes and tag to trigger release
git push && git push --tags
```

### Release Process (Maintainers)

1. Merge PRs to `main` branch
2. Run `uv run python scripts/bump_packages.py` to:
   - Determine next version from conventional commits
   - Update all `pyproject.toml` files
   - Sync inter-package dependencies
   - Create release commit and tag
3. Push: `git push && git push --tags`
4. GitHub Actions will automatically:
   - Build all packages
   - Publish to PyPI
   - Create a GitHub Release

## 🚀 Pull Request Process

1.  Fork the repo and create your branch from `main`.
2.  If you've added code that should be tested, add tests.
3.  Ensure the test suite passes.
4.  Make sure your code lints.
5.  Issue that pull request!

---

Happy coding! 🚀
