# spakky-celery

[Celery](https://docs.celeryq.dev/) integration plugin for [Spakky Framework](https://github.com/E5presso/spakky-framework).

Provides AOP-based automatic task dispatch — methods decorated with `@task` are intercepted
and routed to Celery without explicit dispatcher calls.

## Installation

```bash
pip install spakky-celery
```

> **Requires**: `spakky-task` (installed automatically as a dependency)

## Features

- **AOP-based dispatch**: `@task` methods are intercepted by aspects — no manual `dispatch()` calls
- **Two dispatch modes**: `@task` (immediate via `apply()`) and `@task(background=True)` (broker via `send_task()`)
- **Worker-context detection**: Uses Celery's `current_task` to prevent re-dispatch inside workers
- **Auto-registration**: `@TaskHandler` pods are scanned and registered as Celery tasks automatically
- **Full configuration**: Broker URL, serializer, timezone, and more via environment variables

## Configuration

Set environment variables with the `SPAKKY_CELERY__` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `SPAKKY_CELERY__BROKER_URL` | *(required)* | Celery broker URL (e.g., `amqp://user:pass@host:5672//`) |
| `SPAKKY_CELERY__RESULT_BACKEND` | `None` | Result backend URL. `None` disables result storage |
| `SPAKKY_CELERY__APP_NAME` | `spakky-celery` | Celery application name |
| `SPAKKY_CELERY__TASK_SERIALIZER` | `json` | Task message serializer (`json`, `pickle`, `yaml`, `msgpack`) |
| `SPAKKY_CELERY__RESULT_SERIALIZER` | `json` | Result serializer |
| `SPAKKY_CELERY__ACCEPT_CONTENT` | `["json"]` | Accepted content types |
| `SPAKKY_CELERY__TIMEZONE` | `UTC` | IANA timezone (e.g., `Asia/Seoul`) |
| `SPAKKY_CELERY__ENABLE_UTC` | `true` | Use UTC for internal datetime handling |

## Usage

### 1. Define task handlers

```python
from spakky.task import TaskHandler, task


@TaskHandler()
class EmailTaskHandler:
    @task
    def send_email(self, to: str, subject: str, body: str) -> None:
        """Immediate execution — Celery apply() with retry/error handling."""
        send_smtp(to, subject, body)

    @task(background=True)
    def send_bulk_emails(self, recipients: list[str]) -> None:
        """Broker dispatch — sent to Celery worker via send_task()."""
        for recipient in recipients:
            send_smtp(recipient, "Newsletter", "...")
```

### 2. Bootstrap the application

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

import spakky.plugins.celery

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(include={spakky.plugins.celery.PLUGIN_NAME})
    .scan()
    .start()
)
```

### 3. Call task methods normally

```python
handler = app.container.get(EmailTaskHandler)

# Immediate execution (background=False, default)
handler.send_email("user@example.com", "Hello", "World")

# Dispatched to broker (background=True)
handler.send_bulk_emails(["a@example.com", "b@example.com"])
```

The AOP aspect intercepts the calls and routes them to Celery automatically.

### Dispatch Modes

| Decorator | Behavior | Celery API |
|-----------|----------|------------|
| `@task` | Execute immediately, block for result | `Task.apply()` |
| `@task(background=True)` | Dispatch to broker, return immediately | `Celery.send_task()` |

## Components

| Component | Description |
|-----------|-------------|
| `CeleryApp` | Pod wrapping Celery instance and task route registry |
| `CeleryConfig` | Configuration loaded from environment variables |
| `CeleryPostProcessor` | Scans `@TaskHandler` pods and registers methods as Celery tasks |
| `CeleryTaskDispatchAspect` | AOP aspect intercepting sync `@task` calls |
| `AsyncCeleryTaskDispatchAspect` | AOP aspect intercepting async `@task` calls |

## Related Packages

- **`spakky-task`**: Core task abstractions (`@TaskHandler`, `@task`, `TaskRoute`)
- **`spakky-rabbitmq`**: RabbitMQ event transport (can also be used as Celery broker)

## License

MIT License
