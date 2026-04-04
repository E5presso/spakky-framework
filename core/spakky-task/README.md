# spakky-task

Task queue abstraction layer for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-task
```

## Features

- **`@TaskHandler` stereotype**: Marks classes as task handler pods
- **`@task` decorator**: Marks methods as on-demand dispatchable tasks
- **`@schedule` decorator**: Marks methods for periodic execution (interval, daily, crontab)
- **`Crontab` value object**: Python-native cron specification with `Weekday`/`Month` enums
- **Post-processor**: Automatically scans and registers task routes from `@TaskHandler` pods
- **Implementation-agnostic**: Works with any task queue backend (Celery, etc.) via plugins

## Usage

### On-Demand Tasks

`@task` marks methods for on-demand dispatch. The backend plugin (e.g., `spakky-celery`)
intercepts calls via AOP and routes them to the task queue.

```python
from spakky.task import TaskHandler, task


@TaskHandler()
class EmailTaskHandler:
    @task
    def send_email(self, to: str, subject: str, body: str) -> None:
        """Dispatched to the task queue when called."""
        ...
```

### Scheduled Tasks

`@schedule` marks methods for periodic execution. Exactly one of `interval`, `at`, or `crontab`
must be specified.

```python
from datetime import time, timedelta

from spakky.task import TaskHandler, Crontab, Weekday, schedule


@TaskHandler()
class MaintenanceHandler:
    @schedule(interval=timedelta(minutes=30))
    def health_check(self) -> None:
        """Runs every 30 minutes."""
        ...

    @schedule(at=time(3, 0))
    def daily_cleanup(self) -> None:
        """Runs daily at 03:00."""
        ...

    @schedule(crontab=Crontab(weekday=Weekday.MONDAY, hour=9))
    def weekly_report(self) -> None:
        """Runs every Monday at 09:00."""
        ...
```

### Crontab Specification

`Crontab` uses Python-native types instead of cron strings. `None` means "every" (wildcard).

```python
from spakky.task import Crontab, Weekday, Month

# Every Monday at 03:00
Crontab(weekday=Weekday.MONDAY, hour=3)

# Mon/Wed/Fri at 09:00
Crontab(weekday=(Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY), hour=9)

# 1st and 15th of every month at midnight
Crontab(day=(1, 15))

# Every January 1st at midnight
Crontab(month=Month.JANUARY, day=1)
```

**Field order** (descending temporal granularity):

| Field     | Type                              | Default |
|-----------|-----------------------------------|---------|
| `month`   | `Month \| tuple[Month, ...] \| None` | `None` (every) |
| `day`     | `int \| tuple[int, ...] \| None`    | `None` (every) |
| `weekday` | `Weekday \| tuple[Weekday, ...] \| None` | `None` (every) |
| `hour`    | `int`                             | `0`     |
| `minute`  | `int`                             | `0`     |

### Accessing Task Routes

```python
from spakky.task import TaskRegistrationPostProcessor

post_processor = container.get(TaskRegistrationPostProcessor)
routes = post_processor.get_task_routes()
# {<bound method send_email>: TaskRoute(), ...}
```

## Components

| Component | Description |
|-----------|-------------|
| `TaskHandler` | Stereotype decorator for task handler classes |
| `@task` | Method decorator for on-demand task dispatch |
| `@schedule` | Method decorator for periodic execution (`interval`, `at`, `crontab`) |
| `TaskRoute` | Annotation for `@task` methods |
| `ScheduleRoute` | Annotation for `@schedule` methods |
| `Crontab` | Frozen dataclass for cron-like schedule specification |
| `Weekday` | `IntEnum` for day of the week (Monday=0 ... Sunday=6) |
| `Month` | `IntEnum` for month of the year (January=1 ... December=12) |
| `TaskRegistrationPostProcessor` | Scans `@TaskHandler` pods and collects `@task` methods |

## Errors

| Error | Description |
|-------|-------------|
| `TaskNotFoundError` | Task reference not found in the registry |
| `DuplicateTaskError` | Attempting to register an already-registered task |
| `InvalidScheduleSpecificationError` | `@schedule` called with zero or multiple schedule options |

## Related Packages

- **`spakky-celery`**: Celery backend for task dispatch and schedule registration via AOP

## License

MIT License
