# spakky-celery

[Celery](https://docs.celeryq.dev/) integration plugin for [Spakky Framework](https://github.com/E5presso/spakky-framework).

Provides AOP-based automatic task dispatch and periodic schedule registration —
methods decorated with `@task` or `@schedule` are intercepted and routed to Celery
without explicit dispatcher calls.

## Installation

```bash
pip install spakky-celery
```

> **Requires**: `spakky-task` (installed automatically as a dependency)

## Features

- **AOP-based dispatch**: `@task` methods are intercepted by aspects — no manual `dispatch()` calls
- **Broker dispatch**: All `@task` calls are sent to the Celery broker via `send_task()`
- **Schedule registration**: `@schedule` methods are registered to Celery Beat automatically
- **Worker-context detection**: Uses a context key to prevent re-dispatch inside workers
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
from datetime import time, timedelta

from spakky.task import TaskHandler, Crontab, Weekday, task, schedule


@TaskHandler()
class EmailTaskHandler:
    @task
    def send_email(self, to: str, subject: str, body: str) -> None:
        """Dispatched to Celery broker via send_task()."""
        send_smtp(to, subject, body)


@TaskHandler()
class MaintenanceHandler:
    @schedule(interval=timedelta(minutes=30))
    def health_check(self) -> None:
        """Registered as Celery Beat periodic task — runs every 30 minutes."""
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

# Dispatched to broker — AOP intercepts and calls send_task()
handler.send_email("user@example.com", "Hello", "World")
```

The AOP aspect intercepts the calls and routes them to Celery automatically.

### Dispatch Behavior

| Decorator   | Behavior                        | Celery API      |
|-------------|--------------------------------|-----------------|
| `@task`     | Dispatch to broker on each call | `send_task()`   |
| `@schedule` | Register in Celery Beat         | `beat_schedule` |

## Components

| Component | Description |
|-----------|-------------|
| `CeleryConfig` | Configuration loaded from environment variables |
| `CeleryPostProcessor` | Scans `@TaskHandler` pods and registers methods as Celery tasks/schedules |
| `CeleryTaskDispatchAspect` | AOP aspect intercepting sync `@task` calls |
| `AsyncCeleryTaskDispatchAspect` | AOP aspect intercepting async `@task` calls |

## Errors

| Error | Description |
|-------|-------------|
| `InvalidScheduleRouteError` | `ScheduleRoute` has no valid schedule specification |

## Distributed Tracing (Optional)

`spakky-tracing`이 설치되면 태스크 디스패치 시 `TraceContext`가 자동으로 전파됩니다.

```bash
pip install spakky-celery[tracing]
```

- **디스패치 측**: `@task` 호출 시 현재 `TraceContext`를 Celery 메시지 헤더에 주입합니다
- **워커 측**: 수신 태스크에서 `TraceContext`를 추출하여 자식 스팬을 생성합니다
- 헤더가 없으면 새로운 루트 트레이스를 시작합니다

## Related Packages

- **`spakky-task`**: Core task abstractions (`@TaskHandler`, `@task`, `@schedule`, `Crontab`)
- **`spakky-rabbitmq`**: RabbitMQ event transport (can also be used as Celery broker)
- **`spakky-tracing`**: Distributed tracing abstraction (optional, enables context propagation)

## License

MIT License
