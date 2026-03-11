"""Unit tests for TaskHandler stereotype and @task decorator."""

from spakky.core.pod.annotations.pod import Pod

from spakky.task.stereotype.task_handler import TaskHandler, TaskRoute, task


def test_task_handler_is_pod_subclass() -> None:
    """TaskHandler가 Pod의 서브클래스인지 검증한다."""
    assert issubclass(TaskHandler, Pod)


def test_task_handler_exists_returns_true_for_decorated_class() -> None:
    """@TaskHandler로 데코레이트된 클래스에 TaskHandler.exists()가 True를 반환하는지 검증한다."""

    @TaskHandler()
    class SampleTaskHandler:
        pass

    assert TaskHandler.exists(SampleTaskHandler) is True


def test_pod_exists_returns_true_for_task_handler() -> None:
    """@TaskHandler로 데코레이트된 클래스에 Pod.exists()가 True를 반환하는지 검증한다 (MRO 기반 인덱싱)."""

    @TaskHandler()
    class SampleTaskHandler:
        pass

    assert Pod.exists(SampleTaskHandler) is True


def test_task_decorator_applies_task_route() -> None:
    """@task 데코레이터가 메서드에 TaskRoute 어노테이션을 적용하는지 검증한다."""

    @TaskHandler()
    class SampleTaskHandler:
        @task
        def process(self, data: str) -> None:
            pass

    handler = SampleTaskHandler()
    assert TaskRoute.exists(handler.process) is True


def test_task_route_get_returns_annotation() -> None:
    """TaskRoute.get()이 어노테이션을 반환하는지 검증한다."""

    @TaskHandler()
    class SampleTaskHandler:
        @task
        def process(self, data: str) -> None:
            pass

    handler = SampleTaskHandler()
    route = TaskRoute.get(handler.process)
    assert isinstance(route, TaskRoute)


def test_task_route_get_or_none_returns_none_for_unannotated() -> None:
    """TaskRoute.get_or_none()이 어노테이션 없는 메서드에 None을 반환하는지 검증한다."""

    @TaskHandler()
    class SampleTaskHandler:
        def not_a_task(self, data: str) -> None:
            pass

    handler = SampleTaskHandler()
    assert TaskRoute.get_or_none(handler.not_a_task) is None


def test_task_handler_without_task_methods_is_valid() -> None:
    """@task 메서드 없는 @TaskHandler 클래스가 유효한지 검증한다."""

    @TaskHandler()
    class EmptyTaskHandler:
        def regular_method(self) -> None:
            pass

    assert TaskHandler.exists(EmptyTaskHandler) is True


def test_multiple_task_methods_in_handler() -> None:
    """하나의 @TaskHandler에 여러 @task 메서드를 정의할 수 있는지 검증한다."""

    @TaskHandler()
    class MultiTaskHandler:
        @task
        def task_one(self) -> None:
            pass

        @task
        def task_two(self) -> None:
            pass

        def not_a_task(self) -> None:
            pass

    handler = MultiTaskHandler()
    assert TaskRoute.exists(handler.task_one) is True
    assert TaskRoute.exists(handler.task_two) is True
    assert TaskRoute.exists(handler.not_a_task) is False


def test_task_default_background_false() -> None:
    """@task (옵션 없이) 사용 시 background가 False인지 검증한다."""

    @TaskHandler()
    class DefaultTaskHandler:
        @task
        def process(self) -> None:
            pass

    handler = DefaultTaskHandler()
    route = TaskRoute.get(handler.process)
    assert route.background is False


def test_task_with_background_true() -> None:
    """@task(background=True)가 TaskRoute에 저장되는지 검증한다."""

    @TaskHandler()
    class BackgroundTaskHandler:
        @task(background=True)
        def send_email(self) -> None:
            pass

    handler = BackgroundTaskHandler()
    route = TaskRoute.get(handler.send_email)
    assert route.background is True
