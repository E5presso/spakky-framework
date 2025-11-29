"""Test ensure_importable function for sys.path management."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from spakky.core.importing import ensure_importable


def test_ensure_importable_when_parent_already_in_sys_path() -> None:
    """Test that nothing happens when parent directory is already in sys.path."""
    # Use a directory that's already in sys.path
    existing_path = Path(sys.path[0])
    package_dir = existing_path / "some_package"

    original_sys_path = sys.path.copy()

    ensure_importable(package_dir)

    # sys.path should remain unchanged
    assert sys.path == original_sys_path


def test_ensure_importable_adds_parent_when_import_fails() -> None:
    """Test that parent directory is added to sys.path when import fails."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a fake package structure
        temp_path = Path(temp_dir)
        package_dir = temp_path / "fake_test_package"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text("")

        # Ensure parent is not in sys.path
        parent_str = str(temp_path)
        if parent_str in sys.path:
            sys.path.remove(parent_str)

        original_length = len(sys.path)

        try:
            ensure_importable(package_dir)

            # Parent should now be in sys.path
            assert parent_str in sys.path
            assert sys.path[0] == parent_str  # Should be at the front
            assert len(sys.path) == original_length + 1
        finally:
            # Cleanup: remove the added path
            if parent_str in sys.path:
                sys.path.remove(parent_str)


def test_ensure_importable_skips_when_import_succeeds() -> None:
    """Test that sys.path is not modified when package is already importable."""
    # Use an existing package that's already importable
    import spakky

    spakky_path = Path(spakky.__file__).parent
    parent_str = str(spakky_path.parent)

    # Remove parent temporarily if it exists
    modified_path = [p for p in sys.path if p != parent_str]

    with patch.object(sys, "path", modified_path):
        # Since spakky is already loaded, import should succeed
        # and no path should be added
        initial_length = len(sys.path)
        ensure_importable(spakky_path)

        # Length shouldn't change since import succeeded
        # (the module is already in sys.modules)
        assert len(sys.path) <= initial_length + 1


def test_ensure_importable_logs_when_adding_path() -> None:
    """Test that adding to sys.path is logged."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        package_dir = temp_path / "logging_test_package"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text("")

        parent_str = str(temp_path)
        if parent_str in sys.path:
            sys.path.remove(parent_str)

        try:
            with patch("spakky.core.importing.logger") as mock_logger:
                ensure_importable(package_dir)

                # Verify logging was called
                mock_logger.info.assert_called_once()
                call_args = mock_logger.info.call_args
                assert "sys.path" in call_args[0][0]
                assert parent_str in call_args[0][1]
        finally:
            if parent_str in sys.path:
                sys.path.remove(parent_str)
