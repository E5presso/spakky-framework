"""Test pod edge cases for complete coverage."""

from typing import cast
from collections.abc import Callable

import pytest

from spakky.core.pod.annotations.pod import (
    Pod,
    UnexpectedDependencyNameInjectedError,
    UnexpectedDependencyTypeInjectedError,
)


def test_pod_instantiate_with_unexpected_dependency_name() -> None:
    """Pod 인스턴스화 시 예상치 못한 의존성 이름이 주어지면 예외가 발생함을 검증한다."""

    @Pod()
    class SamplePod:
        def __init__(self, expected_dep: int) -> None:
            self.expected_dep = expected_dep

    pod = Pod.get(SamplePod)

    # Try to instantiate with wrong dependency name
    with pytest.raises(UnexpectedDependencyNameInjectedError):
        pod.instantiate({"wrong_name": 42})


def test_pod_instantiate_with_wrong_dependency_type() -> None:
    """Pod 인스턴스화 시 필수 의존성에 None이 주어지면 예외가 발생함을 검증한다."""

    @Pod()
    class SamplePod:
        def __init__(self, required_dep: int) -> None:
            self.required_dep = required_dep

    pod = Pod.get(SamplePod)

    # Try to instantiate with None for required dependency
    with pytest.raises(UnexpectedDependencyTypeInjectedError):
        pod.instantiate({"required_dep": None})


def test_pod_instantiate_with_none_and_default_value() -> None:
    """Pod 인스턴스화 시 None이 주어지면 기본값을 사용함을 검증한다."""

    @Pod()
    class SamplePod:
        def __init__(self, dep: int = 10) -> None:
            self.dep = dep

    pod = Pod.get(SamplePod)

    # Instantiate with None - should use default value
    instance = pod.instantiate({"dep": None})

    assert isinstance(instance, SamplePod)
    assert instance.dep == 10  # Default value used


def test_pod_unresolved_annotated_without_metadata_expect_raw_annotation_dependency() -> (
    None
):
    """Annotated 인자가 하나뿐인 미해결 문자열 어노테이션은 원문 문자열 의존성으로 남음을 검증한다."""
    namespace: dict[str, object] = {"Pod": Pod}
    exec(
        """
@Pod()
class SingleArgumentAnnotatedConsumer:
    def __init__(self, dependency: "Annotated[(MissingSamplePod,)]") -> None:
        self.dependency = dependency

def resolve_dependency() -> tuple[object, list[object]]:
    dependency = Pod.get(SingleArgumentAnnotatedConsumer).dependencies["dependency"]
    return dependency.type_, list(dependency.qualifiers)
""",
        namespace,
    )

    resolve_dependency = cast(
        Callable[[], tuple[object, list[object]]],
        namespace["resolve_dependency"],
    )

    assert resolve_dependency() == ("Annotated[(MissingSamplePod,)]", [])


def test_pod_unresolved_annotated_with_invalid_metadata_expect_raw_annotation_dependency() -> (
    None
):
    """미해결 문자열 어노테이션의 metadata 식이 평가 불가하면 원문 문자열 의존성으로 남음을 검증한다."""
    namespace: dict[str, object] = {"Pod": Pod}
    exec(
        """
@Pod()
class InvalidMetadataAnnotatedConsumer:
    def __init__(self, dependency: "Annotated[MissingSamplePod, 'tier' + 1]") -> None:
        self.dependency = dependency

def resolve_dependency() -> tuple[object, list[object]]:
    dependency = Pod.get(InvalidMetadataAnnotatedConsumer).dependencies["dependency"]
    return dependency.type_, list(dependency.qualifiers)
""",
        namespace,
    )

    resolve_dependency = cast(
        Callable[[], tuple[object, list[object]]],
        namespace["resolve_dependency"],
    )

    assert resolve_dependency() == ("Annotated[MissingSamplePod, 'tier' + 1]", [])
