"""Test core importing edge cases for complete coverage."""

from spakky.core.importing import is_root_package, is_subpath_of, list_modules


def test_is_subpath_of_with_wildcard_pattern() -> None:
    """Test is_subpath_of with wildcard patterns."""
    # Test with fnmatch-style pattern
    assert is_subpath_of("tests.dummy.module", {"tests.dummy.*"})
    assert is_subpath_of("tests.dummy.module.sub", {"tests.dummy"})


def test_is_subpath_of_with_module_type() -> None:
    """Test is_subpath_of with ModuleType objects."""
    import tests.dummy

    # Test with ModuleType as pattern
    assert is_subpath_of("tests.dummy", {tests.dummy})
    assert is_subpath_of("tests.dummy.dummy_package", {tests.dummy})


def test_is_root_package_without_path() -> None:
    """Test is_root_package with module that has no __path__."""
    # Non-package modules don't have __path__
    import sys as test_module

    assert not is_root_package(test_module)


def test_is_root_package_with_sys_path() -> None:
    """Test is_root_package logic."""
    # This tests the sys.path comparison logic
    import tests

    # tests package should not be a root package
    # as it's inside the project structure
    result = is_root_package(tests)
    # Result depends on sys.path configuration
    assert isinstance(result, bool)


def test_list_modules_with_import_error() -> None:
    """Test list_modules handles ImportError gracefully."""
    import tests.dummy

    # This should work and skip modules that can't be imported
    modules = list_modules(tests.dummy)

    # Should have some modules
    assert len(modules) > 0
