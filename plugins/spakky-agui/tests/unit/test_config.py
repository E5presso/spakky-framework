"""Tests for AG-UI adapter configuration."""

from pytest import MonkeyPatch

from spakky.plugins.agui.config import AgUiConfig


def test_agui_config_defaults_expect_documented_values() -> None:
    """AgUiConfig가 문서화된 기본값(path/snapshot 게이트)을 노출한다."""
    config = AgUiConfig()

    assert config.sse_path == "/agui"
    assert config.websocket_path == "/agui/ws"
    assert config.http_stream_path == "/agui/stream"
    assert config.emit_state_snapshot is True
    assert config.messages_snapshot_enabled is False


def test_agui_config_env_override_expect_environment_values(
    monkeypatch: MonkeyPatch,
) -> None:
    """SPAKKY_AGUI_ 환경변수가 설정 필드를 재정의한다."""
    monkeypatch.setenv("SPAKKY_AGUI_SSE_PATH", "/stream/agui")
    monkeypatch.setenv("SPAKKY_AGUI_WEBSOCKET_PATH", "/stream/agui/ws")
    monkeypatch.setenv("SPAKKY_AGUI_HTTP_STREAM_PATH", "/stream/agui/http")
    monkeypatch.setenv("SPAKKY_AGUI_EMIT_STATE_SNAPSHOT", "false")
    monkeypatch.setenv("SPAKKY_AGUI_MESSAGES_SNAPSHOT_ENABLED", "true")

    config = AgUiConfig()

    assert config.sse_path == "/stream/agui"
    assert config.websocket_path == "/stream/agui/ws"
    assert config.http_stream_path == "/stream/agui/http"
    assert config.emit_state_snapshot is False
    assert config.messages_snapshot_enabled is True
