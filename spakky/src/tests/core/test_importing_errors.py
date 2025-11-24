"""Test core importing module for complete coverage."""

import pytest

from spakky.core.importing import resolve_module


def test_resolve_module_with_invalid_string_raises_import_error() -> None:
    """Test that resolve_module raises ImportError for invalid module name."""
    with pytest.raises(ImportError) as exc_info:
        resolve_module("this_module_does_not_exist_at_all")

    assert "Failed to import module" in str(exc_info.value)
