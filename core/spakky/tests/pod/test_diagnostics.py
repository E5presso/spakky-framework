"""Test Pod dependency resolution diagnostics detail rendering."""

from spakky.core.pod.diagnostics import (
    PodCandidateDiagnostic,
    PodDependencyPathNode,
    PodDependencyResolutionDiagnostic,
)


def test_diagnostic_without_dependency_parameter_expect_no_dependency_details() -> None:
    """의존성 파라미터 없이 발생한 실패는 파라미터/요청 타입 detail을 남기지 않음을 검증한다."""
    diagnostic = PodDependencyResolutionDiagnostic(
        failed_pod_name="sample_service",
        failed_pod_type_name="SampleService",
        dependency_parameter_name=None,
        requested_type_name=None,
        path=(
            PodDependencyPathNode(
                pod_name="sample_service",
                pod_type_name="SampleService",
            ),
        ),
    )

    assert diagnostic.as_detail_pairs() == (
        ("failed_pod", "sample_service"),
        ("failed_pod_type", "SampleService"),
        ("dependency_path", "SampleService"),
    )


def test_diagnostic_without_dependency_parameter_expect_candidate_details_preserved() -> (
    None
):
    """의존성 파라미터가 없어도 후보 진단이 있으면 candidates/hints detail은 그대로 남음을 검증한다."""
    diagnostic = PodDependencyResolutionDiagnostic(
        failed_pod_name="sample_service",
        failed_pod_type_name="SampleService",
        dependency_parameter_name=None,
        requested_type_name=None,
        path=(
            PodDependencyPathNode(
                pod_name="sample_service",
                pod_type_name="SampleService",
            ),
        ),
        candidates=(
            PodCandidateDiagnostic(
                pod_name="first",
                pod_type_name="FirstSamplePod",
                is_primary=False,
            ),
        ),
        resolution_hints=("mark exactly one candidate with @Primary",),
    )

    details = dict(diagnostic.as_detail_pairs())

    assert "dependency_parameter" not in details
    assert "requested_type" not in details
    assert details["candidates"] == "first:FirstSamplePod:primary=False"
    assert details["resolution_hints"] == "mark exactly one candidate with @Primary"
