# spakky-logging

Structured logging system for Spakky Framework. Provides contextvars-based log context propagation, configurable formatters (Text, JSON, Pretty), automatic method call logging with masking and timing via AOP, and auto-configuration via PostProcessor.

## Installation

```bash
pip install spakky-logging
```

## Quick Start

### 1. Plugin Auto-Registration

`spakky-logging` is automatically loaded via `load_plugins()`:

```python
app = SpakkyApplication(ApplicationContext()).load_plugins().scan(my_app).start()
```

### 2. Annotate Methods with `@logged`

```python
from spakky.plugins.logging import logged

class UserService:
    @logged()
    async def create_user(self, name: str, password: str) -> User:
        ...
```

### 3. Configure (Optional)

Override defaults via `LoggingConfig`:

```python
from spakky.plugins.logging import LoggingConfig, LogFormat

config = LoggingConfig(
    level="DEBUG",
    format=LogFormat.JSON,
    mask_keys=frozenset({"password", "token", "secret"}),
    slow_threshold_ms=500,
)
```

### 4. Log Context Propagation

Bind contextual key-value pairs that are automatically included in all log records:

```python
from spakky.plugins.logging import LogContext

LogContext.bind(request_id="req-123", user_id="u-456")

with LogContext.scope(trace_id="t-789"):
    # All logs within this block include trace_id
    ...
```

## Features

| Feature                     | Description                                                |
| --------------------------- | ---------------------------------------------------------- |
| `@logged()` annotation      | AOP-based automatic method call/result/error logging       |
| `LogContext`                | Contextvars-based structured context propagation           |
| `ContextInjectingFilter`    | Injects LogContext values into every `LogRecord`           |
| `SpakkyTextFormatter`       | Pipe-separated text format                                 |
| `SpakkyJsonFormatter`       | One JSON object per line                                   |
| `SpakkyPrettyFormatter`     | ANSI-colored multi-column format for development           |
| `LoggingConfig`             | `@Configuration` pod for centralized logging configuration |
| `LoggingSetupPostProcessor` | Auto-configures root logger on application start           |
| Sensitive data masking      | Masks `password`, `token`, `secret` etc. in log output     |
| Slow call detection         | Warns when method execution exceeds threshold              |
| Result truncation           | Truncates long return values in log output                 |

## License

MIT License
