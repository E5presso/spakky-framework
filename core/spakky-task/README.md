# spakky-task

[Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 태스크 큐 추상화 레이어입니다.

## 설치

```bash
pip install spakky-task
```

## 주요 기능

- **`@TaskHandler` stereotype**: 클래스를 task handler pod로 표시합니다.
- **`@task` decorator**: 메서드를 on-demand dispatch 가능한 task로 표시합니다.
- **`@schedule` decorator**: 메서드를 주기 실행 대상(interval, daily, crontab)으로 표시합니다.
- **`Crontab` value object**: `Weekday`/`Month` enum을 사용하는 Python-native cron 명세
- **Post-processor**: `@TaskHandler` pod에서 task route를 자동 스캔하고 등록합니다.
- **구현체 중립**: 플러그인을 통해 Celery 등 임의의 태스크 큐 백엔드와 동작

## 사용법

### On-demand 태스크

`@task`는 메서드를 on-demand dispatch 대상으로 표시합니다. 백엔드 플러그인(예: `spakky-celery`)은 AOP로 호출을 가로채 task queue로 라우팅합니다.

```python
from spakky.task import TaskHandler, task


@TaskHandler()
class EmailTaskHandler:
    @task
    def send_email(self, to: str, subject: str, body: str) -> None:
        """Dispatched to the task queue when called."""
        ...
```

### 예약 태스크

`@schedule`는 메서드를 주기 실행 대상으로 표시합니다. `interval`, `at`, `crontab` 중 정확히 하나를 지정해야 합니다.

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

### Crontab 명세

`Crontab`은 cron 문자열 대신 Python-native 타입을 사용합니다. `None`은 "every"(wildcard)를 의미합니다.

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

**필드 순서**(시간 단위가 큰 것부터):

| 필드     | 타입                              | 기본값 |
|-----------|-----------------------------------|---------|
| `month`   | `Month \| tuple[Month, ...] \| None` | `None`(every) |
| `day`     | `int \| tuple[int, ...] \| None`    | `None`(every) |
| `weekday` | `Weekday \| tuple[Weekday, ...] \| None` | `None`(every) |
| `hour`    | `int`                             | `0`     |
| `minute`  | `int`                             | `0`     |

### Task route 접근

```python
from spakky.task import TaskRegistrationPostProcessor

post_processor = container.get(TaskRegistrationPostProcessor)
routes = post_processor.get_task_routes()
# {<bound method send_email>: TaskRoute(), ...}
```

## 구성 요소

| 구성 요소 | 설명 |
|-----------|-------------|
| `TaskHandler` | 태스크 핸들러 클래스용 stereotype decorator |
| `@task` | on-demand 태스크 dispatch용 메서드 decorator |
| `@schedule` | 주기 실행용 메서드 decorator(`interval`, `at`, `crontab`) |
| `TaskRoute` | `@task` 메서드용 annotation |
| `ScheduleRoute` | `@schedule` 메서드용 annotation |
| `Crontab` | cron 유사 schedule 명세용 frozen dataclass |
| `Weekday` | 요일용 `IntEnum`(Monday=0 ... Sunday=6) |
| `Month` | 월용 `IntEnum`(January=1 ... December=12) |
| `TaskRegistrationPostProcessor` | `@TaskHandler` pod를 스캔하고 `@task` 메서드를 수집 |

## 에러

| 에러 | 설명 |
|-------|-------------|
| `TaskNotFoundError` | registry에서 task reference를 찾을 수 없음 |
| `DuplicateTaskError` | 이미 등록된 task를 다시 등록하려는 경우 |
| `InvalidScheduleSpecificationError` | `@schedule` called with zero or multiple schedule options |

## 관련 패키지

- **`spakky-celery`**: AOP 기반 task dispatch와 schedule 등록을 위한 Celery backend

## 라이선스

MIT License
