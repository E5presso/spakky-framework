# spakky-task

Task queue abstraction layer for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-task
```

## Features

- **`@TaskHandler` stereotype**: Marks classes as task handler pods
- **`@task` decorator**: Marks methods as dispatchable tasks
- **Background mode**: `@task(background=True)` for broker dispatch, `@task` for immediate execution
- **Post-processor**: Automatically scans and registers task routes from `@TaskHandler` pods
- **Implementation-agnostic**: Works with any task queue backend (Celery, etc.) via plugins

## Usage

### Define a Task Handler

```python
from spakky.task import TaskHandler, task


@TaskHandler()
class EmailTaskHandler:
    @task
    def send_email(self, to: str, subject: str, body: str) -> None:
        """Executed immediately (default, background=False)."""
        ...

    @task(background=True)
    def send_bulk_emails(self, recipients: list[str]) -> None:
        """Dispatched to task queue (background=True)."""
        ...
```

### Dispatch Modes

| Decorator | `background` | Behavior |
|-----------|:------------:|----------|
| `@task` | `False` (default) | Execute immediately via task runtime (e.g., Celery `apply()`) |
| `@task(background=True)` | `True` | Dispatch to message broker for async processing |

The actual dispatch mechanism is provided by a backend plugin (e.g., `spakky-celery`).
`spakky-task` itself only provides the abstractions and route registration.

### Accessing Task Routes

```python
from spakky.task import TaskRegistrationPostProcessor

post_processor = container.get(TaskRegistrationPostProcessor)
routes = post_processor.get_task_routes()
# {<bound method send_email>: TaskRoute(background=False), ...}
```

## Components

| Component | Description |
|-----------|-------------|
| `TaskHandler` | Stereotype decorator for task handler classes |
| `@task` | Method decorator with `background` parameter |
| `TaskRoute` | Annotation storing task metadata (`background` flag) |
| `TaskRegistrationPostProcessor` | Scans `@TaskHandler` pods and collects `@task` methods |

## Errors

| Error | Description |
|-------|-------------|
| `TaskNotFoundError` | Task reference not found in the registry |
| `DuplicateTaskError` | Attempting to register an already-registered task |

## Related Packages

- **`spakky-celery`**: Celery backend for task dispatch via AOP

## License

MIT License
