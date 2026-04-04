# Celery 태스크

`spakky-celery`는 `@task` 데코레이터가 붙은 메서드를 Celery 태스크로 자동 등록합니다.

---

## 동작 원리

1. `@TaskHandler` 클래스의 `@task` 메서드를 Celery에 자동 등록
2. 메서드 호출 시 `CeleryTaskDispatchAspect`가 `celery.send_task()`로 변환
3. Celery worker에서 실행 후 결과 반환

---

## 설정

`CeleryConfig`는 `@Configuration`이므로 환경변수에서 자동 로딩됩니다.
함수 Pod로 `Celery` 인스턴스를 생성하면 `CeleryConfig`가 자동 주입됩니다.

```python
from celery import Celery
from spakky.core.pod.annotations.pod import Pod
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.plugins.celery.common.config import CeleryConfig
import spakky.plugins.celery
import apps

@Pod()
def get_celery(config: CeleryConfig) -> Celery:
    return Celery(main=config.app_name, broker=config.broker_url)

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(include={spakky.plugins.celery.PLUGIN_NAME})
    .scan(apps)
    .add(get_celery)
    .start()
)
```

환경변수 예시:

```bash
export SPAKKY_CELERY__BROKER_URL=amqp://guest:guest@localhost:5672//
export SPAKKY_CELERY__APP_NAME=myapp
```

---

## 태스크 정의

```python
from spakky.task.stereotype.task_handler import TaskHandler, task

@TaskHandler()
class EmailTaskHandler:
    _email_service: EmailService

    def __init__(self, email_service: EmailService) -> None:
        self._email_service = email_service

    @task
    def send_welcome_email(self, to: str, name: str) -> None:
        """환영 이메일 발송"""
        self._email_service.send(
            to=to,
            subject=f"환영합니다, {name}!",
            body=f"안녕하세요, {name}님...",
        )

    @task
    def send_report(self, to: str, report_id: str) -> None:
        """리포트 이메일 발송"""
        self._email_service.send(
            to=to,
            subject="리포트",
            body=f"리포트 ID: {report_id}",
        )
```

---

## 태스크 호출

### 일반 호출 → Celery로 디스패치

`@task` 메서드를 호출하면 Aspect가 가로채서 `send_task()`로 디스패치합니다.
반환값은 `spakky-task`의 추상 타입인 `AbstractTaskResult`입니다.

```python
from spakky.task.interfaces.task_result import AbstractTaskResult

handler = app.container.get(type_=EmailTaskHandler)

# @task가 Aspect에 의해 celery.send_task()로 변환됨
result = handler.send_welcome_email(to="user@example.com", name="John")
assert isinstance(result, AbstractTaskResult)
print(result.task_id)  # 디스패치된 태스크 ID
print(result.get())    # 완료까지 블로킹 후 결과 반환
```

### Celery worker 내부에서 호출

Celery worker 내에서 같은 `@task` 메서드를 호출하면 `send_task()` 없이 **직접 실행**됩니다.

```python
# Celery worker 컨텍스트 내부
# → send_task() 호출 없이 실제 메서드 실행
handler.send_welcome_email(to="user@example.com", name="John")
```

---

## 비동기 디스패치

```python
@TaskHandler()
class AsyncEmailHandler:
    @task
    async def send_async_email(self, to: str) -> None:
        """비동기 태스크"""
        await external_api.send(to=to)

# 비동기 호출 → send_task()로 자동 디스패치
result = await handler.send_async_email(to="user@example.com")
assert isinstance(result, AbstractTaskResult)
```

---

## 비동기 결과 조회

`result.get()`은 블로킹 호출이므로 asyncio 이벤트 루프를 차단합니다.
FastAPI 등 asyncio 기반 환경에서는 `await result.get_async()`를 사용하세요.

```python
from spakky.task.interfaces.task_result import AbstractTaskResult

handler = app.container.get(type_=EmailTaskHandler)

result = handler.send_welcome_email(to="user@example.com", name="John")
assert isinstance(result, AbstractTaskResult)
print(result.task_id)              # 디스패치된 태스크 ID

# asyncio 환경: 이벤트 루프를 차단하지 않고 결과 조회
value = await result.get_async()   # run_in_executor로 블로킹 get()을 비동기 래핑

# 동기 환경: 블로킹 방식으로 결과 조회 (이벤트 루프 없는 경우)
value = result.get()
```

---

## 분산 트레이싱 (Optional)

`spakky-tracing`이 설치되면 태스크 디스패치 시 `TraceContext`가 자동으로 전파됩니다.

```bash
pip install spakky-celery[tracing]
```

- **디스패치 측**: `@task` 호출 시 현재 `TraceContext`를 Celery 메시지 헤더에 주입합니다
- **워커 측**: 수신 태스크에서 `TraceContext`를 추출하여 자식 스팬을 생성합니다
- 헤더가 없으면 새로운 루트 트레이스를 시작합니다

별도 설정이나 코드 변경 없이, 플러그인 로드만으로 동작합니다.

---

## 자동 등록 확인

`CeleryPostProcessor`가 `@TaskHandler`를 감지하면 자동으로 Celery에 등록합니다.
태스크 이름은 `{모듈}.{클래스}.{메서드}` 형식의 정규화된 이름(FQCN)입니다.

```python
celery_app: Celery = app.container.get(type_=Celery)

# 등록된 태스크 확인 (모듈 경로 포함)
# 예: apps.handlers 모듈에 정의된 경우
assert "apps.handlers.EmailTaskHandler.send_welcome_email" in celery_app.tasks
assert "apps.handlers.EmailTaskHandler.send_report" in celery_app.tasks
```
