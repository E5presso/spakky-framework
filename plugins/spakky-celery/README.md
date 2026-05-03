# spakky-celery

[Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 [Celery](https://docs.celeryq.dev/) 통합 플러그인입니다.

AOP 기반 자동 task dispatch와 주기 schedule 등록을 제공합니다.
`@task` 또는 `@schedule`로 장식된 메서드는 명시적인 dispatcher 호출 없이 가로채져 Celery로 라우팅됩니다.

## 설치

```bash
pip install spakky-celery
```

> **필수 의존성**: `spakky-task`, `spakky-tracing`(의존성으로 자동 설치)

## 주요 기능

- **AOP 기반 dispatch**: `@task` 메서드는 aspect가 가로채며 수동 `dispatch()` 호출이 필요 없습니다.
- **Broker dispatch**: 모든 `@task` 호출은 `send_task()`를 통해 Celery broker로 전송됩니다.
- **Schedule 등록**: `@schedule` 메서드는 Celery Beat에 자동 등록됩니다.
- **Worker context 감지**: context key로 worker 내부 재dispatch 방지
- **자동 등록**: `@TaskHandler` pod를 스캔해 Celery task로 자동 등록합니다.
- **전체 설정**: broker URL, serializer, timezone 등을 환경변수로 설정

## 설정

`SPAKKY_CELERY__` 접두사로 환경변수를 설정합니다.

| 변수 | 기본값 | 설명 |
|----------|---------|-------------|
| `SPAKKY_CELERY__BROKER_URL` | *(필수)* | Celery broker URL(예: `amqp://user:pass@host:5672//`) |
| `SPAKKY_CELERY__RESULT_BACKEND` | `None` | result backend URL. `None`이면 result storage 비활성 |
| `SPAKKY_CELERY__APP_NAME` | `spakky-celery` | Celery application 이름 |
| `SPAKKY_CELERY__TASK_SERIALIZER` | `json` | task message serializer (`json`, `pickle`, `yaml`, `msgpack`) |
| `SPAKKY_CELERY__RESULT_SERIALIZER` | `json` | result serializer |
| `SPAKKY_CELERY__ACCEPT_CONTENT` | `["json"]` | 허용 content type |
| `SPAKKY_CELERY__TIMEZONE` | `UTC` | IANA timezone(예: `Asia/Seoul`) |
| `SPAKKY_CELERY__ENABLE_UTC` | `true` | 내부 datetime 처리에 UTC 사용 |

## 사용법

### 1. Task handler 정의

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

### 2. 애플리케이션 부트스트랩

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

### 3. Task 메서드 일반 호출

```python
handler = app.container.get(EmailTaskHandler)

# broker로 dispatch됨: AOP가 가로채 send_task() 호출
handler.send_email("user@example.com", "Hello", "World")
```

AOP aspect가 호출을 가로채 Celery로 자동 라우팅합니다.

### Dispatch 동작

| 데코레이터   | 동작                        | Celery API      |
|-------------|--------------------------------|-----------------|
| `@task`     | 호출마다 broker로 dispatch | `send_task()`   |
| `@schedule` | Celery Beat에 등록         | `beat_schedule` |

## 구성 요소

| 구성 요소 | 설명 |
|-----------|-------------|
| `CeleryConfig` | 환경변수에서 로드되는 설정 |
| `CeleryPostProcessor` | `@TaskHandler` pod를 스캔하고 메서드를 Celery task/schedule로 등록 |
| `CeleryTaskDispatchAspect` | 동기 `@task` 호출을 가로채는 AOP aspect |
| `AsyncCeleryTaskDispatchAspect` | 비동기 `@task` 호출을 가로채는 AOP aspect |

## 에러

| 에러 | 설명 |
|-------|-------------|
| `InvalidScheduleRouteError` | `ScheduleRoute` has no valid schedule specification |

## 분산 트레이싱

`spakky-tracing`은 필수 의존성으로 자동 설치됩니다. `ITracePropagator`가 컨테이너에 등록되어 있으면 태스크 디스패치 시 `TraceContext`가 자동으로 전파됩니다.

- **디스패치 측**: `@task` 호출 시 현재 `TraceContext`를 Celery 메시지 헤더에 주입합니다
- **워커 측**: 수신 태스크에서 `TraceContext`를 추출하여 자식 스팬을 생성합니다
- 헤더가 없으면 새로운 루트 트레이스를 시작합니다

## 관련 패키지

- **`spakky-task`**: core task 추상화(`@TaskHandler`, `@task`, `@schedule`, `Crontab`)
- **`spakky-rabbitmq`**: RabbitMQ event transport(Celery broker로도 사용 가능)
- **`spakky-tracing`**: 분산 트레이싱 추상화(필수, context propagation 활성화)

## 라이선스

MIT License
