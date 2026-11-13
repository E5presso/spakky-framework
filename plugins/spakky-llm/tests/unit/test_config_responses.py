"""Configuration tests for OpenAI Responses profiles and routes."""

import pytest
from pydantic import SecretStr, ValidationError

from spakky.plugins.llm.config import (
    LlmConfig,
    LlmModelRoute,
    LlmProfile,
    LlmProviderApi,
    LlmReasoningEffort,
    OpenAICompatibleDialect,
)


def _chatgpt_profile() -> LlmProfile:
    return LlmProfile(
        provider="openai",
        api=LlmProviderApi.OPENAI_RESPONSES,
        openai_dialect=OpenAICompatibleDialect.CHATGPT,
        credential_provider="chatgpt",
    )


def test_chatgpt_profile_expect_responses_api_with_credential_provider() -> None:
    """A ChatGPT sign-in profile names a credential provider instead of a key."""
    profile = LlmProfile.model_validate(
        {
            "provider": "openai",
            "api": "openai-responses",
            "openai_dialect": "chatgpt",
            "credential_provider": " chatgpt ",
        }
    )

    assert profile.api is LlmProviderApi.OPENAI_RESPONSES
    assert profile.openai_dialect is OpenAICompatibleDialect.CHATGPT
    assert profile.credential_provider == "chatgpt"
    assert profile.api_key_value() is None


def test_standard_responses_profile_expect_static_api_key() -> None:
    """An API-key Responses profile keeps the standard dialect."""
    profile = LlmProfile(
        provider="openai",
        api=LlmProviderApi.OPENAI_RESPONSES,
        api_key=SecretStr("secret"),
    )

    assert profile.openai_dialect is OpenAICompatibleDialect.STANDARD
    assert profile.credential_provider is None


@pytest.mark.parametrize(
    ("values", "error_type"),
    [
        (
            {
                "provider": "openai",
                "api": "openai-chat-completions",
                "openai_dialect": "chatgpt",
            },
            "llm_profile_dialect",
        ),
        (
            {
                "provider": "openai",
                "api": "openai-responses",
                "openai_dialect": "vllm",
            },
            "llm_profile_dialect",
        ),
        (
            {
                "provider": "openai",
                "api": "openai-chat-completions",
                "credential_provider": "chatgpt",
            },
            "llm_profile_credential_provider_api",
        ),
        (
            {
                "provider": "openai",
                "api": "openai-responses",
                "api_key": "secret",
                "credential_provider": "chatgpt",
            },
            "llm_profile_credential_source",
        ),
        (
            {
                "provider": "openai",
                "api": "openai-responses",
                "credential_provider": " ",
            },
            "llm_profile_text",
        ),
    ],
)
def test_invalid_responses_profile_expect_validation_error(
    values: dict[str, str],
    error_type: str,
) -> None:
    """Dialects and credential sources are rejected outside their API family."""
    with pytest.raises(ValidationError) as raised:
        LlmProfile.model_validate(values)

    assert raised.value.errors()[0]["type"] == error_type


def test_reasoning_effort_on_responses_route_expect_accepted() -> None:
    """Reasoning effort is configured per model route of a Responses profile."""
    config = LlmConfig(
        default_model="builder/primary",
        profiles={"chatgpt": _chatgpt_profile()},
        models={
            "builder/primary": LlmModelRoute.model_validate(
                {"profile": "chatgpt", "model": "gpt-served", "reasoning_effort": "low"}
            )
        },
    )

    assert config.models["builder/primary"].reasoning_effort is LlmReasoningEffort.LOW


def test_reasoning_effort_on_other_api_expect_validation_error() -> None:
    """Reasoning effort is rejected for profiles that cannot honor it."""
    with pytest.raises(ValidationError) as raised:
        LlmConfig(
            default_model="assistant/default",
            profiles={
                "chat": LlmProfile(
                    provider="openai",
                    api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
                    api_key=SecretStr("secret"),
                )
            },
            models={
                "assistant/default": LlmModelRoute(
                    profile="chat",
                    model="gpt-served",
                    reasoning_effort=LlmReasoningEffort.HIGH,
                )
            },
        )

    assert raised.value.errors()[0]["type"] == "llm_model_route_reasoning_effort"
