# Spakky Framework - AI Coding Instructions

> **References**: API usage examples → `README.md`, Coding standards & conventions → `CONTRIBUTING.md`, Event architecture → `ARCHITECTURE.md`

## Overview

Spring-inspired DI/IoC framework for Python 3.11+ with AOP and plugin system. Uses `uv` workspace monorepo.

- **Core** (`core/`): `spakky` (DI/AOP), `spakky-domain` (DDD), `spakky-data` (Repository/Transaction), `spakky-event` (Event handling)
- **Plugins** (`plugins/`): `spakky-fastapi`, `spakky-rabbitmq`, `spakky-kafka`, `spakky-security`, `spakky-typer`, `spakky-sqlalchemy`
- Each package: `src/spakky/...` (source), `tests/` (tests)

## Key API Reference

| Decorator / Class | Import Path | Purpose |
|---|---|---|
| `@Pod(name=, scope=)` | `spakky.core.pod.annotations.pod` | Register class/function as managed bean |
| `@Primary` | `spakky.core.pod.annotations.primary` | Mark preferred implementation |
| `@Order(n)` | `spakky.core.pod.annotations.order` | Control execution order |
| `@Aspect()` / `@AsyncAspect()` | `spakky.core.aop.aspect` | Sync/Async aspect decorator |
| `IAsyncAspect` / `IAspect` | `spakky.core.aop.interfaces.aspect` | Aspect interfaces |
| `@Before` / `@After` / `@Around` / `@AfterReturning` / `@AfterRaising` | `spakky.core.aop.pointcut` | AOP pointcut decorators |
| `@Logging()` | `spakky.core.aspects.logging` | Built-in logging annotation |
| `@Controller` | `spakky.core.stereotype.controller` | Base controller stereotype |
| `@UseCase` | `spakky.core.stereotype.usecase` | Business logic stereotype |
| `@ApiController(prefix)` | `spakky.plugins.fastapi.stereotypes.api_controller` | FastAPI REST controller |
| `@CliController(group)` | `spakky.plugins.typer.stereotypes.cli_controller` | Typer CLI controller |
| `@EventHandler` / `@on_event` | `spakky.event.stereotype.event_handler` | Event handler stereotype |
| `SpakkyApplication` | `spakky.core.application.application` | App builder (`.load_plugins()` → `.add()` → `.scan()` → `.start()`) |
| `ApplicationContext` | `spakky.core.application.application_context` | IoC container context |

**Pod Scopes**: `SINGLETON` (default), `PROTOTYPE`, `CONTEXT`, `DEFINITION` (metadata-only)

**Logging**: Use `getLogger(__name__)` at module level. Do NOT inject loggers.

**Type Safety (Absolute Rule)**: `Any` type is prohibited (99% rule). Use `TypeVar`, `Protocol`, `object`, or `Union` instead. See `CONTRIBUTING.md` for details.

**Type Safety**:
- Avoid `Any` type; use `TypeVar`, `Protocol`, `object`, or `Union` instead.
- `Any` is allowed only for unavoidable cases (e.g., external library invariant generics) with inline comment.
- `# type: ignore` comments are **prohibited**. Find a proper type-safe solution.

**Magic Numbers**: Avoid magic numbers. Define named constants with docstrings. See `CONTRIBUTING.md` for details.

## Monorepo Rules

### Tests

**CRITICAL**: Tests MUST be run from each package directory, NOT from root.

```bash
cd core/spakky && uv run pytest        # Core
cd core/spakky-domain && uv run pytest  # Domain
cd plugins/spakky-fastapi && uv run pytest  # etc.
```

### Test Style

- **Function-based only** (no `class TestXxx`)
- **Naming**: `test_<function>_<scenario>_expect_<result>`
- **Docstrings**: Required for each test function

### Dependencies

```bash
uv sync --all-packages --all-extras  # Root: install all
uv sync --all-extras                 # Sub-package: install only that package
```

## AI Agent Rules

### Tool Usage

1. **Prefer integrated tools** (`runTests`, `get_errors`, `read_file`, etc.) over terminal commands
2. **Always prefix** Python commands with `uv run` (venv is NOT activated in PTY)
3. **NEVER use multiline quoted commands** in terminal (heredocs, `python -c "..."`) — PTY will hang
4. **Use file tools** (`create_file`, `replace_string_in_file`) instead of `cat`/`echo` redirections
5. **Verify terminal commands** by executing them before documenting

### Documentation Maintenance Rules

**This section MUST be preserved in all future versions.**

1. **Code-first**: Every statement must be backed by actual code. No hallucinations.
2. **Cross-reference**: Find the exact code line before documenting any feature.
3. **Sync all docs**: Changes to codebase → update all relevant markdown files (NOT `CHANGELOG.md`, it's auto-generated).
4. **Sub-package READMEs**: Always check/update READMEs in all `core/*/README.md` and `plugins/*/README.md`.
5. **Priority**: Code > `CONTRIBUTING.md` > this file > `README.md`. If docs contradict code, update docs.
6. **Verification checklist**: File paths, class/function names, method signatures, import paths, env var prefixes — all must be verified against actual code.
