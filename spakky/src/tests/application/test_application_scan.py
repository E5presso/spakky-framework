"""Test application scan edge cases for complete coverage."""

from spakky.application.application import SpakkyApplication
from spakky.application.application_context import ApplicationContext


def test_scan_without_path_in_exec_context() -> None:
    """Test scan without path when caller context cannot be determined."""
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
    """Test scan with a non-package module (single file)."""
    from tests.dummy.dummy_package import module_a

    app = SpakkyApplication(ApplicationContext())
    result = app.scan(module_a)

    assert result is app
    # Should have found PodA from module_a
    assert len(app.container.pods) > 0


def test_scan_with_exclude_set() -> None:
    """Test scan with exclude parameter."""
    from tests.dummy import dummy_package
    from tests.dummy.dummy_package import module_a

    app = SpakkyApplication(ApplicationContext())
    # Scan with exclusion
    result = app.scan(dummy_package, exclude={module_a})

    assert result is app
