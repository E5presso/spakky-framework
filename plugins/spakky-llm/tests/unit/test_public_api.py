"""Tests for the deliberately small spakky-llm package API."""

import spakky.plugins.llm as llm_api
from spakky.plugins.llm import PLUGIN_NAME


def test_public_api_exports_only_plugin_identity() -> None:
    """구현 세부 타입은 root package의 하위호환 alias로 노출하지 않는다."""
    assert PLUGIN_NAME.name == "spakky-llm"
    assert llm_api.__all__ == ["PLUGIN_NAME"]
