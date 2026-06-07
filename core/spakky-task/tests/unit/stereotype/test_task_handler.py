"""Unit tests for TaskHandler stereotype and @task decorator."""

from dataclasses import dataclass

from spakky.auth import protected, public_access, require_role, require_scope
from spakky.core.pod.annotations.pod import Pod

from spakky.task.stereotype.task_handler import (
    TaskHandler,
    TaskRoute,
    _task_auth_requirement_from_annotation,
    collect_task_auth_metadata,
    task,
)


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


def test_task_decorator_is_simple_callable() -> None:
    """@task 데코레이터가 인자 없이 바로 메서드에 적용되는지 검증한다."""

    @TaskHandler()
    class SimpleTaskHandler:
        @task
        def process(self) -> None:
            pass

    handler = SimpleTaskHandler()
    route = TaskRoute.get(handler.process)
    assert isinstance(route, TaskRoute)


def test_task_route_collects_protected_auth_metadata_without_auth_argument() -> None:
    """@task metadata는 AuthContext method argument 없이 보호 요구사항을 보존한다."""

    @require_role("role:admin", tenant="tenant:1")
    class ProtectedTaskHandler:
        @task
        @require_scope("tasks:run")
        def process(self) -> None:
            return None

    handler = ProtectedTaskHandler()
    metadata = collect_task_auth_metadata(
        handler.process,
        owner_type=ProtectedTaskHandler,
    )

    assert metadata.protected
    assert [(item.kind, item.ref, item.tenant) for item in metadata.requirements] == [
        ("ROLE", "role:admin", "tenant:1"),
        ("SCOPE", "tasks:run", None),
    ]


def test_task_route_collects_public_auth_metadata() -> None:
    """@task metadata는 명시적 public_access marker도 보존한다."""

    class PublicTaskHandler:
        @task
        @public_access
        def process(self) -> None:
            return None

    handler = PublicTaskHandler()
    metadata = collect_task_auth_metadata(handler.process)

    assert metadata.public_access
    assert not metadata.protected


def test_task_route_auth_metadata_defaults_to_public_unprotected() -> None:
    """auth decorator가 없는 task route는 보호 요구사항을 갖지 않는다."""

    @TaskHandler()
    class SampleTaskHandler:
        @task
        def process(self) -> None:
            return None

    route = TaskRoute.get(SampleTaskHandler().process)

    assert not route.auth_metadata.public_access
    assert not route.auth_metadata.protected


def test_protected_marker_on_task_records_authenticated_requirement() -> None:
    """@protected task는 authenticated marker requirement를 task metadata로 노출한다."""

    class ProtectedTaskHandler:
        @task
        @protected
        def process(self) -> None:
            return None

    handler = ProtectedTaskHandler()
    metadata = collect_task_auth_metadata(handler.process)

    assert metadata.requirements[0].kind == "AUTHENTICATED"


def test_invalid_auth_annotation_payload_is_ignored() -> None:
    """비정상 auth annotation payload는 task metadata requirement로 변환하지 않는다."""
    assert _task_auth_requirement_from_annotation(object()) is None


def test_invalid_auth_requirement_ref_is_ignored() -> None:
    """비정상 auth requirement ref는 task metadata requirement로 변환하지 않는다."""

    @dataclass
    class BrokenRequirement:
        kind: str | None
        ref: object

    @dataclass
    class BrokenProtectedRequirement:
        requirement: BrokenRequirement

    annotation = BrokenProtectedRequirement(
        requirement=BrokenRequirement(kind=None, ref=1)
    )

    assert _task_auth_requirement_from_annotation(annotation) is None


def test_non_string_auth_requirement_fields_are_stringified() -> None:
    """문자열이 아닌 auth metadata 필드는 task route metadata에서 문자열화된다."""

    @dataclass
    class NumericRequirement:
        kind: str
        ref: str
        resource: int
        action: int
        tenant: int

    @dataclass
    class NumericProtectedRequirement:
        requirement: NumericRequirement

    annotation = NumericProtectedRequirement(
        requirement=NumericRequirement(
            kind="POLICY",
            ref="document:1",
            resource=1,
            action=2,
            tenant=3,
        )
    )

    metadata = _task_auth_requirement_from_annotation(annotation)

    assert metadata is not None
    assert metadata.resource == "1"
    assert metadata.action == "2"
    assert metadata.tenant == "3"
