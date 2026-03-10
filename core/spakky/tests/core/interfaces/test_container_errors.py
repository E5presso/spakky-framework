from spakky.core.pod.interfaces.container import CircularDependencyGraphDetectedError


class DummyA:
    """테스트용 더미 클래스 A."""


class DummyB:
    """테스트용 더미 클래스 B."""


def test_circular_dependency_error_empty_chain_expect_message_only() -> None:
    """빈 dependency_chain 시 기본 메시지만 반환함을 검증한다."""
    error = CircularDependencyGraphDetectedError(dependency_chain=[])
    assert str(error) == "Circular dependency graph detected"


def test_circular_dependency_error_with_chain_expect_formatted_path() -> None:
    """dependency_chain이 있을 때 시각적 경로를 포함한 메시지를 반환함을 검증한다."""
    error = CircularDependencyGraphDetectedError(
        dependency_chain=[DummyA, DummyB, DummyA]
    )
    result = str(error)
    assert "Circular dependency graph detected" in result
    assert "Dependency path:" in result
    assert "DummyA" in result
    assert "DummyB" in result
    assert "(CIRCULAR!)" in result


def test_circular_dependency_error_single_element_expect_circular_marker() -> None:
    """단일 요소 체인에서도 CIRCULAR 마커가 표시됨을 검증한다."""
    error = CircularDependencyGraphDetectedError(dependency_chain=[DummyA])
    result = str(error)
    assert "DummyA (CIRCULAR!)" in result
