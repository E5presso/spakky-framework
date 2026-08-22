"""Configuration for the operator-owned multi-provider LLM catalog."""

from collections.abc import Mapping
from enum import StrEnum
from json import loads
from os import environ
from pathlib import Path
from re import fullmatch
from typing import ClassVar, LiteralString, TypedDict, override

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    InitSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from spakky.agent import JsonValue, ModelCapability
from spakky.core.stereotype.configuration import Configuration

from spakky.plugins.llm.constants import (
    DEFAULT_LLM_API_KEY,
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_MAX_RETRIES,
    DEFAULT_LLM_MODEL_REF,
    DEFAULT_LLM_PROFILE,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_LLM_PROVIDER_MODEL,
    DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
    DEFAULT_LLM_STREAM_TIMEOUT_SECONDS,
    SPAKKY_LLM_CONFIG_ENV_PREFIX,
)
from spakky.plugins.llm.cache import LlmCachePolicy
from spakky.plugins.llm.error import LlmConfigurationError, LlmFailureClass
from spakky.plugins.llm.resilience import LlmResiliencePolicy

type LlmScalar = bool | int | float | str


def _reject_duplicate_json_object(
    pairs: list[tuple[str, JsonValue]],
) -> dict[str, JsonValue]:
    """Decode one JSON object while rejecting duplicate keys at every depth."""
    decoded: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in decoded:
            raise PydanticCustomError(
                "llm_environment_duplicate_key",
                "Duplicate JSON key in SPAKKY_LLM catalog: {key}",
                {"key": key},
            )
        decoded[key] = value
    return decoded


def _decode_environment_json(value: str) -> JsonValue:
    """Decode environment JSON without standard-library last-key-wins behavior."""
    return loads(value, object_pairs_hook=_reject_duplicate_json_object)


class _LlmEnvSettingsSource(EnvSettingsSource):
    """Environment source that masks explicit init fields before JSON decoding."""

    __explicit_fields: frozenset[str]

    def __init__(
        self,
        settings_cls: type[BaseSettings],
        template: EnvSettingsSource,
        explicit_fields: frozenset[str],
    ) -> None:
        super().__init__(
            settings_cls,
            case_sensitive=template.case_sensitive,
            env_prefix=template.env_prefix,
            env_nested_delimiter=template.env_nested_delimiter,
            env_nested_max_split=template.env_nested_max_split,
            env_ignore_empty=template.env_ignore_empty,
            env_parse_none_str=template.env_parse_none_str,
            env_parse_enums=template.env_parse_enums,
        )
        self.__explicit_fields = explicit_fields

    @override
    def get_field_value(
        self,
        field: FieldInfo,
        field_name: str,
    ) -> tuple[str | None, str, bool]:
        if field_name in self.__explicit_fields:
            return None, field_name, False
        return super().get_field_value(field, field_name)

    @override
    def prepare_field_value(
        self,
        field_name: str,
        field: FieldInfo,
        value: JsonValue,
        value_is_complex: bool,
    ) -> JsonValue:
        if field_name in self.__explicit_fields:
            return None
        return super().prepare_field_value(
            field_name,
            field,
            value,
            value_is_complex,
        )

    @override
    def decode_complex_value(
        self,
        field_name: str,
        field: FieldInfo,
        value: str,
    ) -> JsonValue:
        return _decode_environment_json(value)


class _LlmDotEnvSettingsSource(DotEnvSettingsSource):
    """Dotenv source with the same explicit-field and duplicate-key policy."""

    __explicit_fields: frozenset[str]

    def __init__(
        self,
        settings_cls: type[BaseSettings],
        template: DotEnvSettingsSource,
        explicit_fields: frozenset[str],
    ) -> None:
        super().__init__(
            settings_cls,
            env_file=template.env_file,
            env_file_encoding=template.env_file_encoding,
            dotenv_filtering=template.dotenv_filtering,
            case_sensitive=template.case_sensitive,
            env_prefix=template.env_prefix,
            env_nested_delimiter=template.env_nested_delimiter,
            env_nested_max_split=template.env_nested_max_split,
            env_ignore_empty=template.env_ignore_empty,
            env_parse_none_str=template.env_parse_none_str,
            env_parse_enums=template.env_parse_enums,
        )
        self.__explicit_fields = explicit_fields

    @override
    def get_field_value(
        self,
        field: FieldInfo,
        field_name: str,
    ) -> tuple[str | None, str, bool]:
        if field_name in self.__explicit_fields:
            return None, field_name, False
        return super().get_field_value(field, field_name)

    @override
    def prepare_field_value(
        self,
        field_name: str,
        field: FieldInfo,
        value: JsonValue,
        value_is_complex: bool,
    ) -> JsonValue:
        if field_name in self.__explicit_fields:
            return None
        return super().prepare_field_value(
            field_name,
            field,
            value,
            value_is_complex,
        )

    @override
    def decode_complex_value(
        self,
        field_name: str,
        field: FieldInfo,
        value: str,
    ) -> JsonValue:
        return _decode_environment_json(value)


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


def _normalized_catalog_key(
    value: str,
    error_type: LiteralString,
    message: LiteralString,
) -> str:
    """Normalize one opaque catalog key without parsing its internal syntax."""
    normalized = value.strip()
    if normalized == "":
        raise PydanticCustomError(error_type, message)
    return normalized


class LlmProviderApi(StrEnum):
    """Native SDK surface used to reach one configured profile."""

    OPENAI_CHAT_COMPLETIONS = "openai-chat-completions"
    ANTHROPIC_MESSAGES = "anthropic-messages"
    GOOGLE_GEMINI_DEVELOPER = "google-gemini-developer"
    GOOGLE_VERTEX = "google-vertex"


class GoogleCredentialStrategy(StrEnum):
    """Explicit credential source for one Google connection profile."""

    API_KEY = "api-key"
    ADC = "adc"
    SERVICE_ACCOUNT_FILE = "service-account-file"


class OpenAICompatibleDialect(StrEnum):
    """Known extensions layered on the OpenAI chat-completions protocol."""

    STANDARD = "standard"
    VLLM = "vllm"


class LlmProfile(BaseModel):
    """Operator-owned connection, backend, and authentication configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, strict=True)
    api: LlmProviderApi
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
    resilience: LlmResiliencePolicy = Field(default_factory=LlmResiliencePolicy)
    openai_dialect: OpenAICompatibleDialect = OpenAICompatibleDialect.STANDARD
    google_credential_strategy: GoogleCredentialStrategy | None = None
    google_project: str | None = None
    google_location: str | None = None
    google_service_account_file: Path | None = None

    @field_validator(
        "provider",
        "base_url",
        "google_project",
        "google_location",
    )
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

    @field_validator("api_key")
    @classmethod
    def _reject_blank_api_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and value.get_secret_value().strip() == "":
            raise PydanticCustomError(
                "llm_profile_api_key",
                "LLM profile API key cannot be blank",
            )
        return value

    @field_validator("google_location")
    @classmethod
    def _validate_google_location(cls, value: str | None) -> str | None:
        if value is not None and fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value) is None:
            raise PydanticCustomError(
                "llm_google_vertex_location",
                "Google location must be a lowercase endpoint-safe identifier",
            )
        return value

    @field_validator("google_service_account_file", mode="before")
    @classmethod
    def _validate_service_account_file(
        cls,
        value: Path | str | None,
    ) -> Path | None:
        if value is None or isinstance(value, Path):
            return value
        stripped = value.strip()
        if stripped == "":
            raise PydanticCustomError(
                "llm_google_service_account_file",
                "Google service-account file cannot be blank",
            )
        return Path(stripped)

    @model_validator(mode="after")
    def _validate_api_specific_options(self) -> "LlmProfile":
        if self.max_retries > 0 and self.resilience.retry.max_attempts > 1:
            raise PydanticCustomError(
                "llm_retry_owner",
                "SDK and orchestration retries cannot both be enabled",
            )
        if (
            self.api != LlmProviderApi.OPENAI_CHAT_COMPLETIONS
            and self.openai_dialect != OpenAICompatibleDialect.STANDARD
        ):
            raise PydanticCustomError(
                "llm_profile_dialect",
                "OpenAI dialect requires the OpenAI chat API",
            )
        if self.api == LlmProviderApi.GOOGLE_GEMINI_DEVELOPER:
            self._validate_gemini_developer_connection()
        elif self.api == LlmProviderApi.GOOGLE_VERTEX:
            self._validate_vertex_connection()
        else:
            self._reject_google_connection_fields()
        return self

    def _validate_gemini_developer_connection(self) -> None:
        if (
            self.google_credential_strategy != GoogleCredentialStrategy.API_KEY
            or self.api_key is None
        ):
            raise PydanticCustomError(
                "llm_google_developer_auth",
                "Gemini Developer API requires an explicit API-key strategy",
            )
        if any(
            value is not None
            for value in (
                self.google_project,
                self.google_location,
                self.google_service_account_file,
            )
        ):
            raise PydanticCustomError(
                "llm_google_developer_vertex_fields",
                "Gemini Developer API forbids Vertex connection fields",
            )

    def _validate_vertex_connection(self) -> None:
        if self.api_key is not None:
            raise PydanticCustomError(
                "llm_google_vertex_api_key",
                "Vertex AI forbids API-key authentication",
            )
        if self.google_project is None or self.google_location is None:
            raise PydanticCustomError(
                "llm_google_vertex_location",
                "Vertex AI requires explicit project and location",
            )
        if self.google_credential_strategy not in (
            GoogleCredentialStrategy.ADC,
            GoogleCredentialStrategy.SERVICE_ACCOUNT_FILE,
        ):
            raise PydanticCustomError(
                "llm_google_vertex_auth",
                "Vertex AI requires an explicit ADC or service-account strategy",
            )
        if (
            self.google_credential_strategy
            == GoogleCredentialStrategy.SERVICE_ACCOUNT_FILE
        ) != (self.google_service_account_file is not None):
            raise PydanticCustomError(
                "llm_google_vertex_service_account",
                "Service-account strategy and file must be configured together",
            )

    def _reject_google_connection_fields(self) -> None:
        if any(
            value is not None
            for value in (
                self.google_credential_strategy,
                self.google_project,
                self.google_location,
                self.google_service_account_file,
            )
        ):
            raise PydanticCustomError(
                "llm_profile_google_fields",
                "Google connection fields require a Google provider API",
            )

    def api_key_value(self) -> str | None:
        """Return the secret only at the provider client construction boundary."""
        if self.api_key is None:
            return None
        return self.api_key.get_secret_value()


class LlmModelRoute(BaseModel):
    """Strict mapping from one opaque model ref to one provider model target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: str = Field(min_length=1, strict=True)
    model: str = Field(min_length=1, strict=True)
    capability: ModelCapability = Field(default_factory=ModelCapability)
    chat_template_kwargs: dict[str, LlmScalar] = Field(default_factory=dict)
    fallbacks: tuple[str, ...] = ()
    fallback_on: frozenset[LlmFailureClass] = frozenset()
    cache: LlmCachePolicy = Field(default_factory=LlmCachePolicy)

    @field_validator("profile")
    @classmethod
    def _normalize_profile(cls, value: str) -> str:
        return _normalized_catalog_key(
            value,
            "llm_model_route_profile",
            "LLM model route profile cannot be blank",
        )

    @field_validator("model")
    @classmethod
    def _normalize_model(cls, value: str) -> str:
        stripped = value.strip()
        if stripped == "":
            raise PydanticCustomError(
                "llm_model_route_model",
                "LLM provider model identifier cannot be blank",
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

    @field_validator("fallbacks")
    @classmethod
    def _normalize_fallbacks(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for model_ref in value:
            key = _normalized_catalog_key(
                model_ref,
                "llm_model_route_fallback",
                "LLM fallback model ref cannot be blank",
            )
            if key in normalized:
                raise PydanticCustomError(
                    "llm_model_route_fallback_duplicate",
                    "LLM fallback model refs must be unique",
                )
            normalized.append(key)
        return tuple(normalized)

    @model_validator(mode="after")
    def _validate_capability(self) -> "LlmModelRoute":
        context_window = self.capability.context_window_tokens
        if context_window is not None and context_window <= 0:
            raise PydanticCustomError(
                "llm_model_route_context_window",
                "LLM model route context window must be positive",
            )
        if (
            len(self.capability.input_modalities) == 0
            or len(self.capability.output_modalities) == 0
        ):
            raise PydanticCustomError(
                "llm_model_route_modalities",
                "LLM model routes require input and output modalities",
            )
        if (len(self.fallbacks) == 0) != (len(self.fallback_on) == 0):
            raise PydanticCustomError(
                "llm_model_route_fallback_policy",
                "Fallback refs and failure allowlist must be configured together",
            )
        return self


def _default_profiles() -> dict[str, LlmProfile]:
    return {
        DEFAULT_LLM_PROFILE: LlmProfile(
            provider=DEFAULT_LLM_PROVIDER,
            api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
            base_url=DEFAULT_LLM_BASE_URL,
            api_key=SecretStr(DEFAULT_LLM_API_KEY),
            openai_dialect=OpenAICompatibleDialect.VLLM,
        )
    }


def _default_models() -> dict[str, LlmModelRoute]:
    return {
        DEFAULT_LLM_MODEL_REF: LlmModelRoute(
            profile=DEFAULT_LLM_PROFILE,
            model=DEFAULT_LLM_PROVIDER_MODEL,
            capability=ModelCapability(
                supports_tools=True,
                supports_structured_output=True,
            ),
        )
    }


class _Unset:
    __slots__ = ()


_UNSET = _Unset()


class _LlmConfigValues(TypedDict, total=False):
    """Known BaseSettings keyword values forwarded by the explicit constructor."""

    default_model: str
    profiles: Mapping[str, LlmProfile]
    models: Mapping[str, LlmModelRoute]


@Configuration()
class LlmConfig(BaseSettings):
    """Operator-owned connection profiles and opaque logical model catalog."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_LLM_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="forbid",
    )

    default_model: str = DEFAULT_LLM_MODEL_REF
    profiles: dict[str, LlmProfile] = Field(default_factory=_default_profiles)
    models: dict[str, LlmModelRoute] = Field(default_factory=_default_models)

    @classmethod
    @override
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Mask explicit fields before strict environment catalog decoding."""
        if (
            not isinstance(init_settings, InitSettingsSource)
            or not isinstance(env_settings, EnvSettingsSource)
            or not isinstance(dotenv_settings, DotEnvSettingsSource)
        ):
            raise LlmConfigurationError
        explicit_fields = frozenset(init_settings.init_kwargs)
        if explicit_fields == frozenset(cls.model_fields):
            return (init_settings,)
        return (
            init_settings,
            _LlmEnvSettingsSource(settings_cls, env_settings, explicit_fields),
            _LlmDotEnvSettingsSource(
                settings_cls,
                dotenv_settings,
                explicit_fields,
            ),
            file_secret_settings,
        )

    @field_validator("default_model")
    @classmethod
    def _validate_default_model_ref(cls, value: str) -> str:
        return _normalized_catalog_key(
            value,
            "llm_default_model",
            "Default LLM model ref cannot be blank",
        )

    @field_validator("profiles")
    @classmethod
    def _validate_profile_names(
        cls,
        value: dict[str, LlmProfile],
    ) -> dict[str, LlmProfile]:
        normalized: dict[str, LlmProfile] = {}
        for name, profile in value.items():
            key = _normalized_catalog_key(
                name,
                "llm_profile_name",
                "LLM profile names must be unique and non-blank",
            )
            if key in normalized:
                raise PydanticCustomError(
                    "llm_profile_name",
                    "LLM profile names must be unique and non-blank",
                )
            normalized[key] = profile
        if len(normalized) == 0:
            raise PydanticCustomError(
                "llm_profiles_empty",
                "At least one LLM profile is required",
            )
        return normalized

    @field_validator("models")
    @classmethod
    def _validate_model_refs(
        cls,
        value: dict[str, LlmModelRoute],
    ) -> dict[str, LlmModelRoute]:
        normalized: dict[str, LlmModelRoute] = {}
        for model_ref, route in value.items():
            key = _normalized_catalog_key(
                model_ref,
                "llm_model_ref",
                "LLM model refs must be unique and non-blank",
            )
            if key in normalized:
                raise PydanticCustomError(
                    "llm_model_ref",
                    "LLM model refs must be unique and non-blank",
                )
            normalized[key] = route
        if len(normalized) == 0:
            raise PydanticCustomError(
                "llm_models_empty",
                "At least one LLM model route is required",
            )
        return normalized

    @model_validator(mode="after")
    def _validate_catalog_references(self) -> "LlmConfig":
        if self.default_model not in self.models:
            raise PydanticCustomError(
                "llm_default_model_missing",
                "Default LLM model ref must exist in models",
            )
        for model_ref, route in self.models.items():
            profile = self.profiles.get(route.profile)
            if profile is None:
                raise PydanticCustomError(
                    "llm_model_profile_missing",
                    "Every LLM model route profile must exist in profiles",
                )
            if (
                len(route.chat_template_kwargs) > 0
                and profile.openai_dialect != OpenAICompatibleDialect.VLLM
            ):
                raise PydanticCustomError(
                    "llm_model_route_chat_template",
                    "Chat template kwargs require a vLLM connection profile",
                )
            for fallback_ref in route.fallbacks:
                if fallback_ref == model_ref:
                    raise PydanticCustomError(
                        "llm_model_route_fallback_self",
                        "LLM model route cannot fallback to itself",
                    )
                if fallback_ref not in self.models:
                    raise PydanticCustomError(
                        "llm_model_route_fallback_missing",
                        "Every LLM fallback ref must exist in models",
                    )
        self._validate_fallback_cycles()
        return self

    def _validate_fallback_cycles(self) -> None:
        visited: set[str] = set()
        active: set[str] = set()

        def visit(model_ref: str) -> None:
            if model_ref in active:
                raise PydanticCustomError(
                    "llm_model_route_fallback_cycle",
                    "LLM fallback graph cannot contain cycles",
                )
            if model_ref in visited:
                return
            active.add(model_ref)
            for fallback_ref in self.models[model_ref].fallbacks:
                visit(fallback_ref)
            active.remove(model_ref)
            visited.add(model_ref)

        for model_ref in self.models:
            visit(model_ref)

    def __init__(
        self,
        *,
        default_model: str | _Unset = _UNSET,
        profiles: Mapping[str, LlmProfile] | _Unset = _UNSET,
        models: Mapping[str, LlmModelRoute] | _Unset = _UNSET,
    ) -> None:
        values: _LlmConfigValues = {}
        if not isinstance(default_model, _Unset):
            values["default_model"] = default_model
        if not isinstance(profiles, _Unset):
            values["profiles"] = profiles
        if not isinstance(models, _Unset):
            values["models"] = models
        if len(values) != len(self.__class__.model_fields):
            _reject_unknown_prefixed_environment_fields(
                frozenset(field.casefold() for field in self.__class__.model_fields)
            )
        super().__init__(**values)
