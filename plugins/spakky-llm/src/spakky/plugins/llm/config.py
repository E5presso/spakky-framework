"""Configuration for the multi-provider LLM plugin."""

from enum import StrEnum
from os import environ
from typing import ClassVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

from spakky.plugins.llm.constants import (
    DEFAULT_ANTHROPIC_MAX_TOKENS,
    DEFAULT_LLM_API_KEY,
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_MAX_RETRIES,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROFILE,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
    DEFAULT_LLM_STREAM_TIMEOUT_SECONDS,
    SPAKKY_LLM_CONFIG_ENV_PREFIX,
)

type LlmScalar = bool | int | float | str


def _reject_unknown_prefixed_environment_fields(
    allowed_fields: frozenset[str],
) -> None:
    """Fail closed when a prefixed environment key targets no setting field."""
    folded_prefix = SPAKKY_LLM_CONFIG_ENV_PREFIX.casefold()
    for key in environ:
        folded_key = key.casefold()
        if not folded_key.startswith(folded_prefix):
            continue
        root_field = folded_key[len(folded_prefix) :].split("__", maxsplit=1)[0]
        if root_field not in allowed_fields:
            raise PydanticCustomError(
                "llm_environment_field",
                "Unknown SPAKKY_LLM environment field: {field}",
                {"field": root_field},
            )


class LlmProviderApi(StrEnum):
    """Native SDK surface used to reach one configured profile."""

    OPENAI_CHAT_COMPLETIONS = "openai-chat-completions"
    ANTHROPIC_MESSAGES = "anthropic-messages"
    GOOGLE_GENERATE_CONTENT = "google-generate-content"


class OpenAICompatibleDialect(StrEnum):
    """Known extensions layered on the OpenAI chat-completions protocol."""

    STANDARD = "standard"
    VLLM = "vllm"


class LlmProfile(BaseModel):
    """Allowlisted connection and model defaults for one LLM backend."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    api: LlmProviderApi
    model: str = Field(min_length=1)
    base_url: str | None = None
    api_key: SecretStr | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    request_timeout_seconds: float = Field(
        default=DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
        gt=0,
    )
    stream_timeout_seconds: float = Field(
        default=DEFAULT_LLM_STREAM_TIMEOUT_SECONDS,
        gt=0,
    )
    max_retries: int = Field(default=DEFAULT_LLM_MAX_RETRIES, ge=0)
    stream_enabled: bool = True
    context_window_tokens: int | None = Field(default=None, gt=0)
    supports_reasoning: bool = False
    supports_token_counting: bool = False
    openai_dialect: OpenAICompatibleDialect = OpenAICompatibleDialect.STANDARD
    chat_template_kwargs: dict[str, LlmScalar] = Field(default_factory=dict)
    include_thoughts: bool = False
    anthropic_max_tokens: int = Field(default=DEFAULT_ANTHROPIC_MAX_TOKENS, gt=0)

    @field_validator("provider", "model", "base_url")
    @classmethod
    def _strip_nonblank_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if stripped == "":
            raise PydanticCustomError(
                "llm_profile_text",
                "LLM profile text fields cannot be blank",
            )
        return stripped

    @field_validator("chat_template_kwargs")
    @classmethod
    def _normalize_chat_template_kwargs(
        cls,
        value: dict[str, LlmScalar],
    ) -> dict[str, LlmScalar]:
        normalized: dict[str, LlmScalar] = {}
        for key, item in value.items():
            if isinstance(item, str) and item.casefold() in ("true", "false"):
                normalized[key] = item.casefold() == "true"
            else:
                normalized[key] = item
        return normalized

    @model_validator(mode="after")
    def _validate_api_specific_options(self) -> "LlmProfile":
        if (
            self.api != LlmProviderApi.OPENAI_CHAT_COMPLETIONS
            and self.openai_dialect != OpenAICompatibleDialect.STANDARD
        ):
            raise PydanticCustomError(
                "llm_profile_dialect",
                "OpenAI dialect requires the OpenAI chat API",
            )
        if (
            self.openai_dialect != OpenAICompatibleDialect.VLLM
            and len(self.chat_template_kwargs) > 0
        ):
            raise PydanticCustomError(
                "llm_profile_chat_template",
                "Chat template kwargs require the vLLM dialect",
            )
        if self.include_thoughts and not self.supports_reasoning:
            raise PydanticCustomError(
                "llm_profile_thoughts",
                "Thought streaming requires reasoning capability",
            )
        if self.include_thoughts and self.api != LlmProviderApi.GOOGLE_GENERATE_CONTENT:
            raise PydanticCustomError(
                "llm_profile_thoughts_api",
                "Thought inclusion requires the Google GenerateContent API",
            )
        if (
            "anthropic_max_tokens" in self.model_fields_set
            and self.api != LlmProviderApi.ANTHROPIC_MESSAGES
        ):
            raise PydanticCustomError(
                "llm_profile_anthropic_tokens",
                "Anthropic max tokens require the Anthropic Messages API",
            )
        return self

    def api_key_value(self) -> str | None:
        """Return the secret only at the provider client construction boundary."""
        if self.api_key is None:
            return None
        return self.api_key.get_secret_value()


def _default_profiles() -> dict[str, LlmProfile]:
    return {
        DEFAULT_LLM_PROFILE: LlmProfile(
            provider=DEFAULT_LLM_PROVIDER,
            api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
            model=DEFAULT_LLM_MODEL,
            base_url=DEFAULT_LLM_BASE_URL,
            api_key=SecretStr(DEFAULT_LLM_API_KEY),
            openai_dialect=OpenAICompatibleDialect.VLLM,
        )
    }


@Configuration()
class LlmConfig(BaseSettings):
    """Runtime configuration containing only operator-allowlisted LLM profiles."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_LLM_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="forbid",
    )

    default_profile: str = DEFAULT_LLM_PROFILE
    profiles: dict[str, LlmProfile] = Field(default_factory=_default_profiles)

    @field_validator("default_profile")
    @classmethod
    def _validate_default_profile_name(cls, value: str) -> str:
        stripped = value.strip()
        if stripped == "":
            raise PydanticCustomError(
                "llm_default_profile",
                "Default LLM profile cannot be blank",
            )
        return stripped

    @field_validator("profiles")
    @classmethod
    def _validate_profile_names(
        cls,
        value: dict[str, LlmProfile],
    ) -> dict[str, LlmProfile]:
        normalized: dict[str, LlmProfile] = {}
        for name, profile in value.items():
            stripped = name.strip()
            if stripped == "" or stripped in normalized:
                raise PydanticCustomError(
                    "llm_profile_name",
                    "LLM profile names must be unique and non-blank",
                )
            normalized[stripped] = profile
        if len(normalized) == 0:
            raise PydanticCustomError(
                "llm_profiles_empty",
                "At least one LLM profile is required",
            )
        return normalized

    @model_validator(mode="after")
    def _validate_default_profile_exists(self) -> "LlmConfig":
        if self.default_profile not in self.profiles:
            raise PydanticCustomError(
                "llm_default_profile_missing",
                "Default LLM profile must exist in profiles",
            )
        return self

    def __init__(self) -> None:
        _reject_unknown_prefixed_environment_fields(
            frozenset(field.casefold() for field in self.__class__.model_fields)
        )
        super().__init__()
