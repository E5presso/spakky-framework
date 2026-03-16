# 태스크 & 스케줄링

`@task`와 `@schedule`로 온디맨드 실행과 정기 실행을 분리합니다.

---

## @task — 온디맨드 태스크

수동으로 호출되거나 큐를 통해 디스패치되는 태스크입니다.

```python
from spakky.task.stereotype.task_handler import TaskHandler, task

@TaskHandler()
class EmailTaskHandler:
    @task
    def send_welcome_email(self, to: str) -> None:
        print(f"환영 이메일 발송: {to}")

    @task
    def send_report(self, to: str, report_id: str) -> None:
        print(f"리포트 {report_id} 발송: {to}")

    def helper_method(self) -> None:
        """@task가 없으므로 일반 메서드"""
        pass
```

---

## @schedule — 정기 실행

세 가지 방식으로 실행 주기를 지정합니다.

### interval — 반복 주기

```python
from datetime import timedelta
from spakky.task.stereotype.schedule import schedule

@TaskHandler()
class MonitoringHandler:
    @schedule(interval=timedelta(minutes=5))
    def check_health(self) -> None:
        """5분마다 실행"""
        print("Health check...")

    @schedule(interval=timedelta(hours=1))
    def collect_metrics(self) -> None:
        """1시간마다 실행"""
        print("Collecting metrics...")
```

### at — 매일 정시 실행

```python
from datetime import time

@TaskHandler()
class DailyHandler:
    @schedule(at=time(3, 0))
    def cleanup(self) -> None:
        """매일 오전 3시에 실행"""
        print("일간 정리 작업...")

    @schedule(at=time(9, 0))
    def morning_report(self) -> None:
        """매일 오전 9시에 실행"""
        print("아침 리포트 생성...")
```

### crontab — Cron 표현식

세밀한 스케줄 제어가 필요할 때 사용합니다.

```python
from spakky.task.stereotype.crontab import Crontab, Weekday, Month

@TaskHandler()
class CronHandler:
    @schedule(
        crontab=Crontab(
            hour=9,
            weekday=(Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY),
        )
    )
    def triweekly_report(self) -> None:
        """월·수·금 오전 9시"""
        print("주 3회 리포트...")

    @schedule(
        crontab=Crontab(
            hour=0,
            minute=0,
            day=1,
            month=(Month.JANUARY, Month.APRIL, Month.JULY, Month.OCTOBER),
        )
    )
    def quarterly_report(self) -> None:
        """분기 첫째 날 자정"""
        print("분기 리포트...")
```

---

## @task와 @schedule 동시 적용

하나의 메서드에 `@task`와 `@schedule`을 함께 적용할 수 있습니다.
온디맨드 디스패치와 정기 실행을 모두 지원하는 태스크가 됩니다.

```python
@TaskHandler()
class MixedHandler:
    @task
    def on_demand_only(self) -> None:
        """수동 호출/큐 디스패치만 가능"""
        pass

    @schedule(interval=timedelta(hours=1))
    def periodic_only(self) -> None:
        """자동 주기 실행만 가능"""
        pass

    @task
    @schedule(interval=timedelta(hours=1))
    def both(self) -> None:
        """수동 호출도 가능하고, 1시간마다 자동 실행도 됨"""
        pass
```

!!! tip "실제 실행은 플러그인이 담당"
`@task`와 `@schedule`은 메타데이터만 부여합니다. 실제 실행은 `spakky-celery` 같은 플러그인이 처리합니다.
