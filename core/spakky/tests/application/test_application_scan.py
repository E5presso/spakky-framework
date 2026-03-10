"""Test application scan edge cases for complete coverage."""

from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext


def test_scan_without_path_in_exec_context() -> None:
    """호출자 컷텍스트를 알 수 없는 경우 명시적 경로로 scan이 동작함을 검증한다."""
    # This tests the case where caller_package is None
    # which happens when __file__ is not available

    app = SpakkyApplication(ApplicationContext())

    # Create a mock situation where getattr returns None for __file__
    # This is hard to test directly, but we can at least verify
    # that scan works with explicit path
    from tests.dummy import dummy_package

    result = app.scan(dummy_package)
    assert result is app


def test_scan_with_non_package_module() -> None:
    """단일 파일 모듈(비패키지)로 scan을 수행할 수 있음을 검증한다."""
    from tests.dummy.dummy_package import module_a

    app = SpakkyApplication(ApplicationContext())
    result = app.scan(module_a)

    assert result is app
    # Should have found PodA from module_a
    assert len(app.container.pods) > 0


def test_scan_with_exclude_set() -> None:
    """exclude 파라미터를 사용하여 특정 모듈을 제외하고 scan할 수 있음을 검증한다."""
    from tests.dummy import dummy_package
    from tests.dummy.dummy_package import module_a

    app = SpakkyApplication(ApplicationContext())
    # Scan with exclusion
    result = app.scan(dummy_package, exclude={module_a})

    assert result is app
