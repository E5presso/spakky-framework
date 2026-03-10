"""Test core importing module for complete coverage."""

import pytest

from spakky.core.common.importing import resolve_module


def test_resolve_module_with_invalid_string_raises_import_error() -> None:
    """존재하지 않는 모듈 이름으로 resolve_module 호출 시 ImportError가 발생함을 검증한다."""
    with pytest.raises(ImportError) as exc_info:
        resolve_module("this_module_does_not_exist_at_all")

    assert "Failed to import module" in str(exc_info.value)
