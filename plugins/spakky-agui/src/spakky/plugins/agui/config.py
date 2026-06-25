"""Configuration for the spakky-agui plugin."""

from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

SPAKKY_AGUI_CONFIG_ENV_PREFIX = "SPAKKY_AGUI_"
"""Environment prefix for AG-UI adapter settings."""

DEFAULT_AGUI_SSE_PATH = "/agui"
"""Default mount path for the AG-UI SSE endpoint."""

DEFAULT_AGUI_WEBSOCKET_PATH = "/agui/ws"
"""Default mount path for the AG-UI WebSocket endpoint."""

DEFAULT_AGUI_HTTP_STREAM_PATH = "/agui/stream"
"""Default mount path for the AG-UI HTTP streaming endpoint."""


@Configuration()
class AgUiConfig(BaseSettings):
    """Settings for the AG-UI adapter."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_AGUI_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    sse_path: str = DEFAULT_AGUI_SSE_PATH
    """Path the AG-UI SSE endpoint is mounted at on the FastAPI application."""

    websocket_path: str = DEFAULT_AGUI_WEBSOCKET_PATH
    """Path the AG-UI WebSocket endpoint is mounted at on the FastAPI application."""

    http_stream_path: str = DEFAULT_AGUI_HTTP_STREAM_PATH
    """Path the AG-UI HTTP streaming endpoint is mounted at on the FastAPI app."""

    emit_state_snapshot: bool = True
    """Whether STATE_SNAPSHOT neutral events are projected to AG-UI; when False
    the projector drops them so a client that ignores shared state is not sent
    redundant snapshots."""

    messages_snapshot_enabled: bool = False
    """Whether a single MESSAGES_SNAPSHOT is emitted before RUN_FINISHED; the
    framework runner emits no message history, so this defaults off and is only
    enabled by a client that wants a (currently empty) snapshot frame."""

    def __init__(self) -> None:
        super().__init__()
