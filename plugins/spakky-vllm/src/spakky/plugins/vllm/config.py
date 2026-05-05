"""Configuration for the spakky-vllm plugin."""

from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

from spakky.plugins.vllm.constants import (
    DEFAULT_VLLM_ENDPOINT_URL,
    DEFAULT_VLLM_MODEL,
    DEFAULT_VLLM_REQUEST_TIMEOUT_SECONDS,
    DEFAULT_VLLM_STREAM_TIMEOUT_SECONDS,
    SPAKKY_VLLM_CONFIG_ENV_PREFIX,
)


@Configuration()
class VllmConfig(BaseSettings):
    """Settings for the OpenAI-compatible vLLM model endpoint."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_VLLM_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    endpoint_url: str = DEFAULT_VLLM_ENDPOINT_URL
    """Base URL for the vLLM OpenAI-compatible API, without a trailing path."""

    model: str = DEFAULT_VLLM_MODEL
    """Model identifier passed to the vLLM chat completions endpoint."""

    request_timeout_seconds: float = DEFAULT_VLLM_REQUEST_TIMEOUT_SECONDS
    """Timeout for non-streaming chat completion requests."""

    stream_timeout_seconds: float = DEFAULT_VLLM_STREAM_TIMEOUT_SECONDS
    """Timeout budget reserved for streaming requests."""

    stream_enabled: bool = True
    """Whether callers may request the streaming model surface."""

    def __init__(self) -> None:
        super().__init__()

    @property
    def chat_completions_url(self) -> str:
        """Return the normalized chat completions URL."""
        return f"{self.endpoint_url.rstrip('/')}/chat/completions"
