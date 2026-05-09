"""Tests for vLLM configuration."""

from spakky.plugins.vllm.config import VllmConfig


def test_config_defaults_expect_local_vllm_endpoint() -> None:
    """기본 설정이 local OpenAI-compatible vLLM endpoint를 가리킨다."""
    config = VllmConfig()

    assert config.endpoint_url == "http://127.0.0.1:8000/v1"
    assert config.model == "default"
    assert config.chat_completions_url == "http://127.0.0.1:8000/v1/chat/completions"


def test_config_normalizes_chat_completion_url_without_double_slash(
    monkeypatch,
) -> None:
    """endpoint URL 끝의 slash는 chat completions path 조립 시 정규화된다."""
    monkeypatch.setenv("SPAKKY_VLLM__ENDPOINT_URL", "http://localhost:9000/v1/")

    config = VllmConfig()

    assert config.chat_completions_url == "http://localhost:9000/v1/chat/completions"


def test_config_loads_chat_template_kwargs_from_nested_env(monkeypatch) -> None:
    """vLLM chat template kwargs can be configured for model-specific switches."""
    monkeypatch.setenv("SPAKKY_VLLM__CHAT_TEMPLATE_KWARGS__ENABLE_THINKING", "false")
    monkeypatch.setenv("SPAKKY_VLLM__CHAT_TEMPLATE_KWARGS__MODE", "qwen")

    config = VllmConfig()

    assert config.chat_template_kwargs == {"enable_thinking": False, "mode": "qwen"}
