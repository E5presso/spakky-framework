"""Tests for CeleryPostProcessor."""

from datetime import time, timedelta
from unittest.mock import MagicMock

from celery import Celery
from celery.schedules import crontab as celery_crontab
from celery.schedules import schedule as celery_schedule
from spakky.core.utils.inspection import get_fully_qualified_name
from spakky.task.stereotype.crontab import Crontab, Weekday
from spakky.task.stereotype.schedule import schedule
from spakky.task.stereotype.task_handler import TaskHandler, task

from spakky.plugins.celery.post_processor import CeleryPostProcessor


@TaskHandler()
class _SampleTaskHandler:
    @task
    def send_email(self, to: str, subject: str) -> None:
        pass

    @task
    def process_data(self, data: str) -> None:
        pass


def _create_celery() -> Celery:
    """테스트용 Celery를 생성한다."""
    return Celery(main="test", broker="memory://")


def _create_post_processor(celery: Celery) -> CeleryPostProcessor:
    """CeleryPostProcessor를 생성하고 Aware 인터페이스를 설정한다."""
    context_mock = MagicMock()
    context_mock.get.return_value = celery

    post_processor = CeleryPostProcessor()
    post_processor.set_application_context(context_mock)
    return post_processor


def test_celery_post_processor_registers_tasks_on_post_process() -> None:
    """CeleryPostProcessor가 post_process()에서 @task 메서드를 Celery 태스크로 등록하는지 검증한다."""
    celery = _create_celery()
    post_processor = _create_post_processor(celery)
    handler = _SampleTaskHandler()

    post_processor.post_process(handler)

    registered_tasks = list(celery.tasks.keys())
    # Use specific prefix to avoid matching tasks from other test modules
    sample_handler_prefix = "tests.unit.test_post_processor._SampleTaskHandler"
    send_email_tasks = [
        t for t in registered_tasks if t == f"{sample_handler_prefix}.send_email"
    ]
    process_data_tasks = [
        t for t in registered_tasks if t == f"{sample_handler_prefix}.process_data"
    ]

    assert len(send_email_tasks) == 1
    assert len(process_data_tasks) == 1


def test_celery_post_processor_collects_task_routes() -> None:
    """CeleryPostProcessor가 post_process()에서 태스크를 Celery에 등록하는지 검증한다."""
    celery = _create_celery()
    post_processor = _create_post_processor(celery)
    handler = _SampleTaskHandler()

    post_processor.post_process(handler)

    sample_handler_prefix = "tests.unit.test_post_processor._SampleTaskHandler"
    assert f"{sample_handler_prefix}.send_email" in celery.tasks
    assert f"{sample_handler_prefix}.process_data" in celery.tasks


def test_celery_post_processor_ignores_non_task_handler_pods() -> None:
    """CeleryPostProcessor가 @TaskHandler가 아닌 Pod를 무시하는지 검증한다."""
    celery = _create_celery()
    post_processor = _create_post_processor(celery)
    initial_task_count = len(celery.tasks)

    class NotATaskHandler:
        def some_method(self) -> None:
            pass

    result = post_processor.post_process(NotATaskHandler())

    assert isinstance(result, NotATaskHandler)
    assert len(celery.tasks) == initial_task_count


def test_celery_post_processor_returns_pod() -> None:
    """CeleryPostProcessor.post_process()가 pod를 반환하는지 검증한다."""
    celery = _create_celery()
    post_processor = _create_post_processor(celery)
    handler = _SampleTaskHandler()

    result = post_processor.post_process(handler)

    assert result is handler


def test_celery_post_processor_registers_wrapper_with_context_isolation() -> None:
    """등록된 래퍼가 실행 시 컨텍스트를 비우고 컨테이너에서 핸들러를 다시 조회하는지 검증한다."""

    @TaskHandler()
    class TrackingTaskHandler:
        def __init__(self) -> None:
            self.calls: list[str] = []

        @task
        def track(self, value: str) -> str:
            self.calls.append(value)
            return value

    celery_mock = MagicMock()
    application_context_mock = MagicMock()
    tracking_handler = TrackingTaskHandler()

    def get_from_context(type_: object) -> object:
        if type_ is Celery:
            return celery_mock
        if type_ is TrackingTaskHandler:
            return tracking_handler
        raise AssertionError(f"Unexpected dependency lookup: {type_}")

    application_context_mock.get.side_effect = get_from_context

    post_processor = CeleryPostProcessor()
    post_processor.set_application_context(application_context_mock)

    post_processor.post_process(tracking_handler)

    # celery.task(name=task_name) returns a decorator, which is called with endpoint
    endpoint = celery_mock.task.return_value.call_args_list[0].args[0]

    result = endpoint("payload")

    application_context_mock.clear_context.assert_called_once()
    assert application_context_mock.get.call_count >= 2
    assert tracking_handler.calls == ["payload"]
    assert result == "payload"


def test_celery_post_processor_registers_async_tasks() -> None:
    """CeleryPostProcessor가 async 메서드를 올바르게 등록하고 실행하는지 검증한다."""

    @TaskHandler()
    class AsyncTaskHandler:
        def __init__(self) -> None:
            self.calls: list[str] = []

        @task
        async def async_task(self, value: str) -> str:
            self.calls.append(value)
            return f"async: {value}"

    celery_mock = MagicMock()
    application_context_mock = MagicMock()
    async_handler = AsyncTaskHandler()

    def get_from_context(type_: object) -> object:
        if type_ is Celery:
            return celery_mock
        if type_ is AsyncTaskHandler:
            return async_handler
        raise AssertionError(f"Unexpected dependency lookup: {type_}")

    application_context_mock.get.side_effect = get_from_context

    post_processor = CeleryPostProcessor()
    post_processor.set_application_context(application_context_mock)

    post_processor.post_process(async_handler)

    endpoint = celery_mock.task.return_value.call_args_list[0].args[0]

    # async endpoint는 asyncio.run()으로 실행되어야 함
    result = endpoint("async_payload")

    application_context_mock.clear_context.assert_called_once()
    assert async_handler.calls == ["async_payload"]
    assert result == "async: async_payload"


# =============================================================================
# Scenario: Schedule registration
# =============================================================================


def test_celery_post_processor_registers_interval_schedule() -> None:
    """CeleryPostProcessor가 @schedule(interval=...) 메서드를 beat_schedule에 등록하는지 검증한다."""

    @TaskHandler()
    class ScheduledHandler:
        @schedule(interval=timedelta(minutes=30))
        def health_check(self) -> None:
            pass

    celery = _create_celery()
    post_processor = _create_post_processor(celery)

    post_processor.post_process(ScheduledHandler())

    task_name = get_fully_qualified_name(ScheduledHandler.health_check)
    assert task_name in celery.conf.beat_schedule
    entry = celery.conf.beat_schedule[task_name]
    assert entry["task"] == task_name
    assert isinstance(entry["schedule"], celery_schedule)


def test_celery_post_processor_registers_at_schedule() -> None:
    """CeleryPostProcessor가 @schedule(at=...) 메서드를 beat_schedule에 crontab으로 등록하는지 검증한다."""

    @TaskHandler()
    class DailyHandler:
        @schedule(at=time(3, 0))
        def daily_cleanup(self) -> None:
            pass

    celery = _create_celery()
    post_processor = _create_post_processor(celery)

    post_processor.post_process(DailyHandler())

    task_name = get_fully_qualified_name(DailyHandler.daily_cleanup)
    assert task_name in celery.conf.beat_schedule
    entry = celery.conf.beat_schedule[task_name]
    assert isinstance(entry["schedule"], celery_crontab)


def test_celery_post_processor_registers_crontab_schedule() -> None:
    """CeleryPostProcessor가 @schedule(crontab=...) 메서드를 beat_schedule에 등록하는지 검증한다."""

    @TaskHandler()
    class WeeklyHandler:
        @schedule(
            crontab=Crontab(
                hour=9, weekday=(Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY)
            )
        )
        def triweekly_report(self) -> None:
            pass

    celery = _create_celery()
    post_processor = _create_post_processor(celery)

    post_processor.post_process(WeeklyHandler())

    task_name = get_fully_qualified_name(WeeklyHandler.triweekly_report)
    assert task_name in celery.conf.beat_schedule
    entry = celery.conf.beat_schedule[task_name]
    assert isinstance(entry["schedule"], celery_crontab)


def test_celery_post_processor_schedule_method_also_registered_as_celery_task() -> None:
    """@schedule 메서드도 Celery task로 등록되는지 검증한다."""

    @TaskHandler()
    class ScheduledHandler:
        @schedule(interval=timedelta(hours=1))
        def periodic_job(self) -> None:
            pass

    celery = _create_celery()
    post_processor = _create_post_processor(celery)

    post_processor.post_process(ScheduledHandler())

    task_name = get_fully_qualified_name(ScheduledHandler.periodic_job)
    assert task_name in celery.tasks


def test_crontab_to_celery_converts_intenum_to_numeric_string() -> None:
    """_crontab_to_celery가 IntEnum(Month, Weekday)을 숫자 문자열로 변환하는지 검증한다."""
    from spakky.task.stereotype.crontab import Month

    crontab = Crontab(
        month=Month.JANUARY,
        weekday=Weekday.MONDAY,
        hour=9,
        minute=30,
    )

    celery_cron = CeleryPostProcessor._crontab_to_celery(crontab)
    cron_dict = vars(celery_cron)

    # IntEnum이 "Month.JANUARY"가 아닌 "1"로 변환되어야 함
    assert cron_dict["_orig_month_of_year"] == "1"  # Month.JANUARY = 1
    assert cron_dict["_orig_day_of_week"] == "0"  # Weekday.MONDAY = 0


def test_crontab_to_celery_converts_tuple_of_intenum_to_numeric_string() -> None:
    """_crontab_to_celery가 IntEnum 튜플을 쉼표로 구분된 숫자 문자열로 변환하는지 검증한다."""
    from spakky.task.stereotype.crontab import Month

    crontab = Crontab(
        month=(Month.JANUARY, Month.JULY),
        weekday=(Weekday.MONDAY, Weekday.FRIDAY),
        hour=12,
    )

    celery_cron = CeleryPostProcessor._crontab_to_celery(crontab)
    cron_dict = vars(celery_cron)

    # 튜플이 "1,7"로 변환되어야 함 (Month.JANUARY=1, Month.JULY=7)
    assert cron_dict["_orig_month_of_year"] == "1,7"
    # Weekday.MONDAY=0, Weekday.FRIDAY=4
    assert cron_dict["_orig_day_of_week"] == "0,4"
