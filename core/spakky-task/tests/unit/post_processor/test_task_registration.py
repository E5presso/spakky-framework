"""Unit tests for TaskRegistrationPostProcessor."""

from spakky.core.pod.annotations.pod import Pod

from spakky.task.post_processor import TaskRegistrationPostProcessor
from spakky.task.stereotype.task_handler import TaskHandler, task


def test_post_processor_is_pod() -> None:
    """TaskRegistrationPostProcessor가 Pod으로 데코레이트되어 있는지 검증한다."""
    assert Pod.exists(TaskRegistrationPostProcessor)


def test_post_processor_ignores_non_task_handler_pods() -> None:
    """TaskRegistrationPostProcessor가 @TaskHandler가 아닌 Pod을 무시하는지 검증한다."""

    @Pod()
    class RegularPod:
        @task
        def some_method(self) -> None:
            pass

    processor = TaskRegistrationPostProcessor()
    pod = RegularPod()
    result = processor.post_process(pod)

    assert result is pod
    assert len(processor.get_task_routes()) == 0


def test_post_processor_registers_task_methods() -> None:
    """TaskRegistrationPostProcessor가 @task 메서드를 등록하는지 검증한다."""

    @TaskHandler()
    class SampleTaskHandler:
        @task
        def process_data(self, data: str) -> None:
            pass

    processor = TaskRegistrationPostProcessor()
    handler = SampleTaskHandler()
    result = processor.post_process(handler)

    assert result is handler
    routes = processor.get_task_routes()
    assert len(routes) == 1
    assert handler.process_data in routes


def test_post_processor_registers_multiple_task_methods() -> None:
    """TaskRegistrationPostProcessor가 여러 @task 메서드를 등록하는지 검증한다."""

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

    processor = TaskRegistrationPostProcessor()
    handler = MultiTaskHandler()
    processor.post_process(handler)

    routes = processor.get_task_routes()
    assert len(routes) == 2
    assert handler.task_one in routes
    assert handler.task_two in routes


def test_post_processor_returns_pod_unmodified() -> None:
    """TaskRegistrationPostProcessor가 pod을 수정 없이 반환하는지 검증한다."""

    @TaskHandler()
    class SampleTaskHandler:
        @task
        def process(self) -> None:
            pass

    processor = TaskRegistrationPostProcessor()
    handler = SampleTaskHandler()
    result = processor.post_process(handler)

    assert result is handler


def test_get_task_routes_returns_copy() -> None:
    """get_task_routes()가 내부 딕셔너리의 복사본을 반환하는지 검증한다."""

    @TaskHandler()
    class SampleTaskHandler:
        @task
        def process(self) -> None:
            pass

    processor = TaskRegistrationPostProcessor()
    handler = SampleTaskHandler()
    processor.post_process(handler)

    routes1 = processor.get_task_routes()
    routes2 = processor.get_task_routes()

    assert routes1 is not routes2
    assert routes1 == routes2
