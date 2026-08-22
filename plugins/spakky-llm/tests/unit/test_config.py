"""Tests for multi-provider LLM configuration."""

from json import dumps

import pytest
from pydantic import SecretStr, ValidationError
from pydantic_core import PydanticCustomError

from spakky.plugins.llm.config import (
    LlmConfig,
    LlmProfile,
    LlmProviderApi,
    OpenAICompatibleDialect,
)


def test_config_defaults_to_local_vllm_profile() -> None:
    """기본 설정은 공식 OpenAI SDK로 접근하는 local vLLM profile이다."""
    config = LlmConfig()
    profile = config.profiles["default"]

    assert config.default_profile == "default"
    assert profile.provider == "vllm"
    assert profile.api == LlmProviderApi.OPENAI_CHAT_COMPLETIONS
    assert profile.model == "default"
    assert profile.base_url == "http://127.0.0.1:8000/v1"
    assert profile.api_key_value() == "EMPTY"
    assert profile.openai_dialect == OpenAICompatibleDialect.VLLM
    assert profile.max_retries == 0


def test_config_loads_allowlisted_profiles_from_nested_env(monkeypatch) -> None:
    """중첩 환경 변수로 native Anthropic profile을 등록할 수 있다."""
    monkeypatch.setenv("SPAKKY_LLM__DEFAULT_PROFILE", "claude")
    monkeypatch.setenv("SPAKKY_LLM__PROFILES__CLAUDE__PROVIDER", "anthropic")
    monkeypatch.setenv(
        "SPAKKY_LLM__PROFILES__CLAUDE__API",
        "anthropic-messages",
    )
    monkeypatch.setenv("SPAKKY_LLM__PROFILES__CLAUDE__MODEL", "claude-opus-4-1")
    monkeypatch.setenv("SPAKKY_LLM__PROFILES__CLAUDE__API_KEY", "secret")
    monkeypatch.setenv(
        "SPAKKY_LLM__PROFILES__CLAUDE__HEADERS__X_TENANT",
        "tenant-a",
    )

    config = LlmConfig()
    profile = config.profiles["claude"]

    assert profile.provider == "anthropic"
    assert profile.api == LlmProviderApi.ANTHROPIC_MESSAGES
    assert profile.api_key_value() == "secret"
    assert profile.headers == {"x_tenant": "tenant-a"}
    assert "secret" not in repr(profile)


def test_profile_normalizes_vllm_chat_template_boolean_strings() -> None:
    """vLLM dialect option의 환경 변수 boolean 문자열을 정규화한다."""
    profile = LlmProfile(
        provider="vllm",
        api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
        model="qwen",
        openai_dialect=OpenAICompatibleDialect.VLLM,
        chat_template_kwargs={"enable_thinking": "false", "mode": "qwen"},
    )

    assert profile.chat_template_kwargs == {
        "enable_thinking": False,
        "mode": "qwen",
    }
    assert profile.api_key_value() is None


@pytest.mark.parametrize(
    ("kwargs", "error_type"),
    [
        (
            {
                "provider": "anthropic",
                "api": LlmProviderApi.ANTHROPIC_MESSAGES,
                "model": "claude",
                "openai_dialect": OpenAICompatibleDialect.VLLM,
            },
            "llm_profile_dialect",
        ),
        (
            {
                "provider": "google",
                "api": LlmProviderApi.GOOGLE_GENERATE_CONTENT,
                "model": "gemini",
                "chat_template_kwargs": {"mode": "qwen"},
            },
            "llm_profile_chat_template",
        ),
        (
            {
                "provider": "openai",
                "api": LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
                "model": "gpt",
                "chat_template_kwargs": {"mode": "qwen"},
            },
            "llm_profile_chat_template",
        ),
        (
            {
                "provider": "google",
                "api": LlmProviderApi.GOOGLE_GENERATE_CONTENT,
                "model": "gemini",
                "include_thoughts": True,
            },
            "llm_profile_thoughts",
        ),
        (
            {
                "provider": "openai",
                "api": LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
                "model": "gpt",
                "supports_reasoning": True,
                "include_thoughts": True,
            },
            "llm_profile_thoughts_api",
        ),
        (
            {
                "provider": "google",
                "api": LlmProviderApi.GOOGLE_GENERATE_CONTENT,
                "model": "gemini",
                "anthropic_max_tokens": 1024,
            },
            "llm_profile_anthropic_tokens",
        ),
    ],
)
def test_profile_rejects_openai_options_for_native_apis(
    kwargs: dict[str, object],
    error_type: str,
) -> None:
    """OpenAI dialect options cannot leak into native provider profiles."""
    with pytest.raises(ValidationError) as raised:
        LlmProfile.model_validate(kwargs)

    assert raised.value.errors()[0]["type"] == error_type


def test_profile_strips_connection_text_and_wraps_secret() -> None:
    """연결 식별자는 정규화되고 secret은 SecretStr로 보관된다."""
    profile = LlmProfile(
        provider=" openai ",
        api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
        model=" gpt-5.5 ",
        base_url=" https://example.test/v1 ",
        api_key=SecretStr("key"),
    )

    assert profile.provider == "openai"
    assert profile.model == "gpt-5.5"
    assert profile.base_url == "https://example.test/v1"


@pytest.mark.parametrize("field", ["provider", "model", "base_url"])
def test_profile_rejects_blank_connection_text(field: str) -> None:
    """빈 연결 식별자는 allowlist 설정으로 수용하지 않는다."""
    values: dict[str, object] = {
        "provider": "openai",
        "api": LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
        "model": "gpt",
    }
    values[field] = "   "

    with pytest.raises(ValidationError):
        LlmProfile.model_validate(values)


def test_config_rejects_missing_default_profile(monkeypatch) -> None:
    """default profile은 반드시 등록된 allowlist entry를 가리켜야 한다."""
    monkeypatch.setenv("SPAKKY_LLM__DEFAULT_PROFILE", "missing")

    with pytest.raises(ValidationError) as raised:
        LlmConfig()

    assert raised.value.errors()[0]["type"] == "llm_default_profile_missing"


def test_config_rejects_blank_default_profile(monkeypatch) -> None:
    """default profile 이름은 공백일 수 없다."""
    monkeypatch.setenv("SPAKKY_LLM__DEFAULT_PROFILE", "   ")

    with pytest.raises(ValidationError) as raised:
        LlmConfig()

    assert raised.value.errors()[0]["type"] == "llm_default_profile"


@pytest.mark.parametrize(
    "profiles",
    [
        {},
        {
            " ": {
                "provider": "openai",
                "api": "openai-chat-completions",
                "model": "gpt",
            }
        },
        {
            "openai": {
                "provider": "openai",
                "api": "openai-chat-completions",
                "model": "gpt",
            },
            " openai ": {
                "provider": "openai",
                "api": "openai-chat-completions",
                "model": "gpt-backup",
            },
        },
    ],
)
def test_config_rejects_empty_blank_or_normalized_duplicate_profile_names(
    monkeypatch,
    profiles: dict[str, object],
) -> None:
    """Profile allowlist keys remain non-empty and unique after normalization."""
    monkeypatch.setenv("SPAKKY_LLM__PROFILES", dumps(profiles))

    with pytest.raises(ValidationError):
        LlmConfig()


def test_config_rejects_misspelled_nested_profile_fields(monkeypatch) -> None:
    """Connection allowlist typos fail closed instead of selecting an SDK default host."""
    monkeypatch.setenv("SPAKKY_LLM__DEFAULT_PROFILE", "prod")
    monkeypatch.setenv("SPAKKY_LLM__PROFILES__PROD__PROVIDER", "openai")
    monkeypatch.setenv(
        "SPAKKY_LLM__PROFILES__PROD__API",
        "openai-chat-completions",
    )
    monkeypatch.setenv("SPAKKY_LLM__PROFILES__PROD__MODEL", "gpt")
    monkeypatch.setenv("SPAKKY_LLM__PROFILES__PROD__API_KEY", "secret")
    monkeypatch.setenv(
        "SPAKKY_LLM__PROFILES__PROD__BASE_ULR",
        "https://gateway.invalid/v1",
    )

    with pytest.raises(ValidationError) as raised:
        LlmConfig()

    assert raised.value.errors()[0]["type"] == "extra_forbidden"


def test_config_rejects_unknown_top_level_prefixed_environment_fields(
    monkeypatch,
) -> None:
    """Top-level prefix typos cannot silently select the default connection."""
    monkeypatch.setenv("SPAKKY_LLM__PROFILSE__PROD__PROVIDER", "openai")

    with pytest.raises(PydanticCustomError) as raised:
        LlmConfig()

    assert raised.value.type == "llm_environment_field"
