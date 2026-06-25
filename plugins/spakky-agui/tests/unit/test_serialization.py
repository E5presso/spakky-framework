"""Tests for AG-UI adapter JSON serialization helpers."""

from spakky.plugins.agui.serialization import dump_json


def test_dump_json_renders_compact_unicode_text() -> None:
    """dump_json이 공백 없는 compact JSON을 (비 ASCII 보존하여) 만든다."""
    assert dump_json({"city": "서울", "n": 1}) == '{"city":"서울","n":1}'
