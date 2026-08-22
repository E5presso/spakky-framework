"""Tests for operator-owned LLM profiles and logical model routes."""

from json import dumps
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError
from pydantic_core import PydanticCustomError
from pydantic_settings import SettingsError
from pydantic_settings.sources import DefaultSettingsSource
from spakky.agent import ModelCapability, ModelModality

from spakky.plugins.llm.config import (
    GoogleCredentialStrategy,
    LlmConfig,
    LlmModelRoute,
    LlmProfile,
    LlmProviderApi,
    OpenAICompatibleDialect,
)
from spakky.plugins.llm.error import LlmConfigurationError


def _vllm_profile() -> LlmProfile:
    return LlmProfile(
        provider="vllm",
        api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
        base_url="http://127.0.0.1:8000/v1",
        api_key=SecretStr("EMPTY"),
        openai_dialect=OpenAICompatibleDialect.VLLM,
    )


def _developer_profile() -> LlmProfile:
    return LlmProfile(
        provider="google",
        api=LlmProviderApi.GOOGLE_GEMINI_DEVELOPER,
        api_key=SecretStr("developer-secret"),
        google_credential_strategy=GoogleCredentialStrategy.API_KEY,
    )


def _vertex_profile(
    strategy: GoogleCredentialStrategy = GoogleCredentialStrategy.ADC,
    service_account_file: Path | None = None,
) -> LlmProfile:
    return LlmProfile(
        provider="google",
        api=LlmProviderApi.GOOGLE_VERTEX,
        google_credential_strategy=strategy,
        google_project="project-a",
        google_location="us-central1",
        google_service_account_file=service_account_file,
    )


def _route(
    profile: str = "vllm-local",
    model: str = "Qwen/Qwen3-8B",
    capability: ModelCapability | None = None,
) -> LlmModelRoute:
    return LlmModelRoute(
        profile=profile,
        model=model,
        capability=capability or ModelCapability(),
    )


def test_config_defaults_to_neutral_local_vllm_route() -> None:
    """기본 설정은 중립 logical ref에서 local vLLM 연결로 해석된다."""
    config = LlmConfig()
    route = config.models[config.default_model]
    profile = config.profiles[route.profile]

    assert config.default_model == "assistant/default"
    assert route.profile == "vllm-local"
    assert route.model == "default"
    assert route.capability == ModelCapability(
        supports_tools=True,
        supports_structured_output=True,
    )
    assert profile.provider == "vllm"
    assert profile.api == LlmProviderApi.OPENAI_CHAT_COMPLETIONS
    assert profile.base_url == "http://127.0.0.1:8000/v1"
    assert profile.api_key_value() == "EMPTY"
    assert profile.openai_dialect == OpenAICompatibleDialect.VLLM


def test_config_supports_direct_construction_with_opaque_catalog() -> None:
    """호출 예제 형태의 직접 생성이 opaque ref와 full capability를 보존한다."""
    capability = ModelCapability(
        supports_reasoning=True,
        context_window_tokens=1_000_000,
        supports_token_counting=True,
        input_modalities=frozenset({ModelModality.TEXT, ModelModality.IMAGE}),
        output_modalities=frozenset({ModelModality.TEXT}),
        supports_tools=True,
        supports_structured_output=True,
    )
    route = LlmModelRoute(
        profile="google-vertex",
        model="publishers/google/models/gemini-2.5-pro",
        capability=capability,
    )

    config = LlmConfig(
        default_model=" Support/Primary ",
        profiles={" google-vertex ": _vertex_profile()},
        models={" Support/Primary ": route},
    )

    assert config.default_model == "Support/Primary"
    assert config.profiles == {"google-vertex": _vertex_profile()}
    assert config.models == {"Support/Primary": route}
    assert config.models["Support/Primary"].model == (
        "publishers/google/models/gemini-2.5-pro"
    )
    assert config.models["Support/Primary"].capability is capability


def test_config_preserves_case_distinct_opaque_keys() -> None:
    """Trim 외 canonicalization 없이 case-distinct operator keys를 보존한다."""
    config = LlmConfig(
        default_model="support/Primary",
        profiles={"Local": _vllm_profile(), "local": _vllm_profile()},
        models={
            "support/Primary": _route(profile="Local", model="Model/Primary"),
            "support/primary": _route(profile="local", model="Model/Secondary"),
        },
    )

    assert tuple(config.profiles) == ("Local", "local")
    assert tuple(config.models) == ("support/Primary", "support/primary")
    assert config.models[config.default_model].model == "Model/Primary"


def test_config_loads_model_catalog_and_capability_from_environment(
    monkeypatch,
) -> None:
    """환경 설정도 직접 생성과 같은 logical catalog 의미를 만든다."""
    monkeypatch.setenv("SPAKKY_LLM__DEFAULT_MODEL", "Support/Primary")
    monkeypatch.setenv(
        "SPAKKY_LLM__PROFILES",
        dumps(
            {
                "Google-Vertex": {
                    "provider": "google",
                    "api": "google-vertex",
                    "google_credential_strategy": "adc",
                    "google_project": "project-a",
                    "google_location": "us-central1",
                }
            }
        ),
    )
    monkeypatch.setenv(
        "SPAKKY_LLM__MODELS",
        dumps(
            {
                "Support/Primary": {
                    "profile": "Google-Vertex",
                    "model": "publishers/google/models/gemini-2.5-pro",
                    "capability": {
                        "supports_reasoning": True,
                        "context_window_tokens": 1_000_000,
                        "supports_token_counting": True,
                        "input_modalities": ["text", "image"],
                        "output_modalities": ["text"],
                        "supports_tools": True,
                        "supports_structured_output": True,
                    },
                }
            }
        ),
    )

    config = LlmConfig()
    route = config.models["Support/Primary"]

    assert config.default_model == "Support/Primary"
    assert route.profile == "Google-Vertex"
    assert route.capability.input_modalities == frozenset(
        {ModelModality.TEXT, ModelModality.IMAGE}
    )
    assert route.capability.supports_tools is True
    assert route.capability.supports_structured_output is True


def test_full_explicit_config_masks_malformed_and_unrelated_environment(
    monkeypatch,
) -> None:
    """Full explicit config neither decodes same-field env nor audits unrelated keys."""
    monkeypatch.setenv("SPAKKY_LLM__DEFAULT_MODEL", "environment/default")
    monkeypatch.setenv("SPAKKY_LLM__PROFILES", "{malformed")
    monkeypatch.setenv("SPAKKY_LLM__MODELS", "{malformed")
    monkeypatch.setenv("SPAKKY_LLM__UNRELATED", "ignored-by-full-explicit-config")

    config = LlmConfig(
        default_model="support/primary",
        profiles={"vllm-local": _vllm_profile()},
        models={"support/primary": _route()},
    )

    assert config.default_model == "support/primary"
    assert tuple(config.profiles) == ("vllm-local",)
    assert tuple(config.models) == ("support/primary",)


def test_explicit_profiles_mask_malformed_profiles_environment(monkeypatch) -> None:
    """Partial explicit profiles mask only that complex environment field."""
    monkeypatch.setenv("SPAKKY_LLM__DEFAULT_MODEL", "support/primary")
    monkeypatch.setenv("SPAKKY_LLM__PROFILES", "{malformed")
    monkeypatch.setenv(
        "SPAKKY_LLM__PROFILES__VLLM_LOCAL__BASE_ULR",
        "https://nested-invalid.example/v1",
    )
    monkeypatch.setenv(
        "SPAKKY_LLM__MODELS",
        dumps(
            {
                "support/primary": {
                    "profile": "vllm-local",
                    "model": "Qwen/Qwen3-8B",
                }
            }
        ),
    )

    config = LlmConfig(profiles={"vllm-local": _vllm_profile()})

    assert config.models["support/primary"].model == "Qwen/Qwen3-8B"


def test_explicit_models_mask_malformed_models_environment(monkeypatch) -> None:
    """Partial explicit models mask only that complex environment field."""
    monkeypatch.setenv("SPAKKY_LLM__DEFAULT_MODEL", "support/primary")
    monkeypatch.setenv(
        "SPAKKY_LLM__PROFILES",
        dumps(
            {
                "vllm-local": {
                    "provider": "vllm",
                    "api": "openai-chat-completions",
                    "base_url": "http://localhost:8000/v1",
                    "openai_dialect": "vllm",
                }
            }
        ),
    )
    monkeypatch.setenv("SPAKKY_LLM__MODELS", "{malformed")

    config = LlmConfig(models={"support/primary": _route()})

    assert config.profiles["vllm-local"].provider == "vllm"


@pytest.mark.parametrize(
    "models_json",
    [
        (
            '{"support/primary":{"profile":"vllm-local","model":"a"},'
            '"support/primary":{"profile":"vllm-local","model":"b"}}'
        ),
        ('{"support/primary":{"profile":"vllm-local","model":"a","model":"b"}}'),
    ],
)
def test_environment_catalog_json_rejects_duplicate_keys(
    monkeypatch,
    models_json: str,
) -> None:
    """Raw environment JSON rejects duplicate refs and nested route fields."""
    monkeypatch.setenv("SPAKKY_LLM__DEFAULT_MODEL", "support/primary")
    monkeypatch.setenv(
        "SPAKKY_LLM__PROFILES",
        dumps(
            {
                "vllm-local": {
                    "provider": "vllm",
                    "api": "openai-chat-completions",
                    "base_url": "http://localhost:8000/v1",
                    "openai_dialect": "vllm",
                }
            }
        ),
    )
    monkeypatch.setenv("SPAKKY_LLM__MODELS", models_json)

    with pytest.raises(SettingsError) as raised:
        LlmConfig()

    cause = raised.value.__cause__
    assert isinstance(cause, PydanticCustomError)
    assert cause.type == "llm_environment_duplicate_key"


def test_dotenv_catalog_json_rejects_duplicate_keys(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Dotenv catalog decoding uses the same nested duplicate-key rejection."""
    for field in ("DEFAULT_MODEL", "PROFILES", "MODELS"):
        monkeypatch.delenv(f"SPAKKY_LLM__{field}", raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "\n".join(
            (
                "SPAKKY_LLM__DEFAULT_MODEL=support/primary",
                (
                    "SPAKKY_LLM__PROFILES='"
                    '{"vllm-local":{"provider":"vllm",'
                    '"api":"openai-chat-completions",'
                    '"base_url":"http://localhost:8000/v1",'
                    '"openai_dialect":"vllm"}}'
                    "'"
                ),
                (
                    "SPAKKY_LLM__MODELS='"
                    '{"support/primary":{"profile":"vllm-local",'
                    '"model":"a","model":"b"}}'
                    "'"
                ),
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(LlmConfig.model_config, "env_file", dotenv)

    with pytest.raises(SettingsError) as raised:
        LlmConfig()

    cause = raised.value.__cause__
    assert isinstance(cause, PydanticCustomError)
    assert cause.type == "llm_environment_duplicate_key"


def test_settings_source_customization_rejects_unexpected_source_types() -> None:
    """An impossible Pydantic source composition fails through plugin configuration."""
    source = DefaultSettingsSource(LlmConfig)

    with pytest.raises(LlmConfigurationError):
        LlmConfig.settings_customise_sources(
            LlmConfig,
            source,
            source,
            source,
            source,
        )


def test_profile_is_connection_backend_and_auth_only() -> None:
    """구 model·capability 필드는 connection profile alias로 남지 않는다."""
    assert "model" not in LlmProfile.model_fields
    assert "supports_reasoning" not in LlmProfile.model_fields
    assert "context_window_tokens" not in LlmProfile.model_fields
    assert "supports_token_counting" not in LlmProfile.model_fields

    with pytest.raises(ValidationError) as raised:
        LlmProfile.model_validate(
            {
                "provider": "anthropic",
                "api": "anthropic-messages",
                "api_key": "secret",
                "model": "claude",
                "supports_reasoning": True,
            }
        )

    assert {error["type"] for error in raised.value.errors()} == {"extra_forbidden"}


def test_profile_normalizes_connection_text() -> None:
    """연결 profile은 endpoint text만 정규화한다."""
    profile = LlmProfile(
        provider=" vllm ",
        api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
        base_url=" http://localhost:8000/v1 ",
        openai_dialect=OpenAICompatibleDialect.VLLM,
    )

    assert profile.provider == "vllm"
    assert profile.base_url == "http://localhost:8000/v1"
    assert profile.api_key_value() is None


def test_model_route_normalizes_vllm_backend_options() -> None:
    """vLLM model별 chat template option은 route에서 정규화된다."""
    route = LlmModelRoute(
        profile="vllm-local",
        model="Qwen/Qwen3-8B",
        chat_template_kwargs={
            "enable_thinking": "false",
            "enable_tools": "TRUE",
            "mode": "qwen",
            "limit": 2,
        },
    )

    assert route.chat_template_kwargs == {
        "enable_thinking": False,
        "enable_tools": True,
        "mode": "qwen",
        "limit": 2,
    }


@pytest.mark.parametrize("field", ["provider", "base_url"])
def test_profile_rejects_blank_connection_text(field: str) -> None:
    """공백 연결 식별자는 operator-owned profile에 들어갈 수 없다."""
    values = {
        "provider": "openai",
        "api": "openai-chat-completions",
        "api_key": "secret",
        field: " ",
    }

    with pytest.raises(ValidationError):
        LlmProfile.model_validate(values)


@pytest.mark.parametrize(
    ("values", "error_type"),
    [
        (
            {
                "provider": "anthropic",
                "api": "anthropic-messages",
                "openai_dialect": "vllm",
            },
            "llm_profile_dialect",
        ),
        (
            {
                "provider": "openai",
                "api": "openai-chat-completions",
                "chat_template_kwargs": {"mode": "qwen"},
            },
            "extra_forbidden",
        ),
        (
            {
                "provider": "openai",
                "api": "openai-chat-completions",
                "google_project": "project-a",
            },
            "llm_profile_google_fields",
        ),
    ],
)
def test_profile_rejects_backend_options_for_foreign_apis(
    values: dict[str, str | dict[str, str]],
    error_type: str,
) -> None:
    """API별 backend/auth option은 다른 provider profile로 새지 않는다."""
    with pytest.raises(ValidationError) as raised:
        LlmProfile.model_validate(values)

    assert raised.value.errors()[0]["type"] == error_type


def test_gemini_developer_profile_requires_explicit_api_key_strategy() -> None:
    """Gemini Developer API는 operator profile의 API key만 사용한다."""
    profile = _developer_profile()

    assert profile.google_credential_strategy == GoogleCredentialStrategy.API_KEY
    assert profile.api_key_value() == "developer-secret"

    for values in (
        {
            "provider": "google",
            "api": "google-gemini-developer",
            "google_credential_strategy": "api-key",
        },
        {
            "provider": "google",
            "api": "google-gemini-developer",
            "api_key": "secret",
            "google_credential_strategy": "adc",
        },
    ):
        with pytest.raises(ValidationError) as raised:
            LlmProfile.model_validate(values)
        assert raised.value.errors()[0]["type"] == "llm_google_developer_auth"

    with pytest.raises(ValidationError) as raised:
        LlmProfile(
            provider="google",
            api=LlmProviderApi.GOOGLE_GEMINI_DEVELOPER,
            api_key=SecretStr(" "),
            google_credential_strategy=GoogleCredentialStrategy.API_KEY,
        )
    assert raised.value.errors()[0]["type"] == "llm_profile_api_key"


@pytest.mark.parametrize("vertex_field", ["google_project", "google_location"])
def test_gemini_developer_profile_forbids_vertex_coordinates(
    vertex_field: str,
) -> None:
    """Gemini Developer API profile은 Vertex 좌표를 함께 받지 않는다."""
    values = {
        "provider": "google",
        "api": "google-gemini-developer",
        "api_key": "secret",
        "google_credential_strategy": "api-key",
        vertex_field: "ambient-like-value",
    }

    with pytest.raises(ValidationError) as raised:
        LlmProfile.model_validate(values)

    assert raised.value.errors()[0]["type"] == "llm_google_developer_vertex_fields"


def test_gemini_developer_profile_forbids_service_account_file() -> None:
    """Gemini Developer API는 Vertex service-account file을 허용하지 않는다."""
    with pytest.raises(ValidationError) as raised:
        LlmProfile(
            provider="google",
            api=LlmProviderApi.GOOGLE_GEMINI_DEVELOPER,
            api_key=SecretStr("secret"),
            google_credential_strategy=GoogleCredentialStrategy.API_KEY,
            google_service_account_file=Path("/mounted/google.json"),
        )

    assert raised.value.errors()[0]["type"] == "llm_google_developer_vertex_fields"


def test_vertex_profile_accepts_only_explicit_adc_or_service_account() -> None:
    """Vertex AI는 명시 좌표와 선택된 credential strategy를 요구한다."""
    adc = _vertex_profile()
    service = _vertex_profile(
        GoogleCredentialStrategy.SERVICE_ACCOUNT_FILE,
        Path("/mounted/google.json"),
    )

    assert adc.google_credential_strategy == GoogleCredentialStrategy.ADC
    assert adc.google_service_account_file is None
    assert service.google_credential_strategy == (
        GoogleCredentialStrategy.SERVICE_ACCOUNT_FILE
    )
    assert service.google_service_account_file == Path("/mounted/google.json")


@pytest.mark.parametrize(
    ("updates", "error_type"),
    [
        ({"api_key": "secret"}, "llm_google_vertex_api_key"),
        ({"google_project": None}, "llm_google_vertex_location"),
        ({"google_location": None}, "llm_google_vertex_location"),
        ({"google_location": "us-central1/evil"}, "llm_google_vertex_location"),
        ({"google_credential_strategy": "api-key"}, "llm_google_vertex_auth"),
        (
            {"google_credential_strategy": "service-account-file"},
            "llm_google_vertex_service_account",
        ),
        (
            {"google_service_account_file": "/mounted/unexpected.json"},
            "llm_google_vertex_service_account",
        ),
    ],
)
def test_vertex_profile_rejects_ambiguous_or_incomplete_auth(
    updates: dict[str, str | None],
    error_type: str,
) -> None:
    """Vertex AI의 ambient 추론 여지가 있는 조합은 fail closed 된다."""
    values: dict[str, str | None] = {
        "provider": "google",
        "api": "google-vertex",
        "google_credential_strategy": "adc",
        "google_project": "project-a",
        "google_location": "us-central1",
    }
    values.update(updates)

    with pytest.raises(ValidationError) as raised:
        LlmProfile.model_validate(values)

    assert raised.value.errors()[0]["type"] == error_type


@pytest.mark.parametrize("value", ["", " "])
def test_google_service_account_file_rejects_blank_text(value: str) -> None:
    """Mounted credential path는 공백 문자열일 수 없다."""
    with pytest.raises(ValidationError) as raised:
        LlmProfile(
            provider="google",
            api=LlmProviderApi.GOOGLE_VERTEX,
            google_credential_strategy=GoogleCredentialStrategy.SERVICE_ACCOUNT_FILE,
            google_project="project-a",
            google_location="us-central1",
            google_service_account_file=value,
        )

    assert raised.value.errors()[0]["type"] == "llm_google_service_account_file"


def test_model_route_normalizes_refs_without_splitting_slashes() -> None:
    """route profile과 physical model은 slash를 해석하지 않고 보존한다."""
    route = LlmModelRoute(
        profile=" OpenRouter ",
        model=" anthropic/claude-sonnet-4 ",
    )

    assert route.profile == "OpenRouter"
    assert route.model == "anthropic/claude-sonnet-4"


@pytest.mark.parametrize(
    ("field", "value", "error_type"),
    [
        ("profile", " ", "llm_model_route_profile"),
        ("model", " ", "llm_model_route_model"),
    ],
)
def test_model_route_rejects_blank_text(
    field: str,
    value: str,
    error_type: str,
) -> None:
    """route의 내부 profile과 provider model은 nonblank다."""
    values = {"profile": "openrouter", "model": "model-id", field: value}

    with pytest.raises(ValidationError) as raised:
        LlmModelRoute.model_validate(values)

    assert raised.value.errors()[0]["type"] == error_type


@pytest.mark.parametrize(
    ("capability", "error_type"),
    [
        (ModelCapability(context_window_tokens=0), "llm_model_route_context_window"),
        (
            ModelCapability(input_modalities=frozenset()),
            "llm_model_route_modalities",
        ),
        (
            ModelCapability(output_modalities=frozenset()),
            "llm_model_route_modalities",
        ),
    ],
)
def test_model_route_rejects_invalid_capability(
    capability: ModelCapability,
    error_type: str,
) -> None:
    """route capability는 실행 전에 유효한 window와 modality를 요구한다."""
    with pytest.raises(ValidationError) as raised:
        _route(capability=capability)

    assert raised.value.errors()[0]["type"] == error_type


def test_model_route_rejects_unknown_fields() -> None:
    """Strict route는 caller raw endpoint나 credential override를 받지 않는다."""
    with pytest.raises(ValidationError) as raised:
        LlmModelRoute.model_validate(
            {
                "profile": "openrouter",
                "model": "model-id",
                "api_key": "caller-secret",
            }
        )

    assert raised.value.errors()[0]["type"] == "extra_forbidden"


def test_config_rejects_chat_template_options_for_non_vllm_route() -> None:
    """Model-specific vLLM options cannot leak into a standard OpenAI route."""
    standard = LlmProfile(
        provider="openrouter",
        api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
        base_url="https://openrouter.example/v1",
        api_key=SecretStr("secret"),
    )

    with pytest.raises(ValidationError) as raised:
        LlmConfig(
            default_model="support/primary",
            profiles={"openrouter": standard},
            models={
                "support/primary": LlmModelRoute(
                    profile="openrouter",
                    model="anthropic/claude",
                    chat_template_kwargs={"enable_thinking": True},
                )
            },
        )

    assert raised.value.errors()[0]["type"] == "llm_model_route_chat_template"


@pytest.mark.parametrize(
    ("profiles", "error_type"),
    [
        ({}, "llm_profiles_empty"),
        ({" ": _vllm_profile()}, "llm_profile_name"),
        (
            {"Local": _vllm_profile(), " Local ": _vllm_profile()},
            "llm_profile_name",
        ),
    ],
)
def test_config_rejects_invalid_profile_catalog(
    profiles: dict[str, LlmProfile],
    error_type: str,
) -> None:
    """Profile catalog key는 정규화 뒤 nonblank·unique여야 한다."""
    with pytest.raises(ValidationError) as raised:
        LlmConfig(
            default_model="support/primary",
            profiles=profiles,
            models={"support/primary": _route()},
        )

    assert raised.value.errors()[0]["type"] == error_type


@pytest.mark.parametrize(
    ("models", "error_type"),
    [
        ({}, "llm_models_empty"),
        ({" ": _route()}, "llm_model_ref"),
        (
            {"Support/Primary": _route(), " Support/Primary ": _route()},
            "llm_model_ref",
        ),
    ],
)
def test_config_rejects_invalid_model_catalog(
    models: dict[str, LlmModelRoute],
    error_type: str,
) -> None:
    """Logical model refs는 opaque key 전체를 정규화한 뒤 unique다."""
    with pytest.raises(ValidationError) as raised:
        LlmConfig(
            default_model="support/primary",
            profiles={"vllm-local": _vllm_profile()},
            models=models,
        )

    assert raised.value.errors()[0]["type"] == error_type


@pytest.mark.parametrize(
    ("default_model", "route", "error_type"),
    [
        (" ", _route(), "llm_default_model"),
        ("support/missing", _route(), "llm_default_model_missing"),
        (
            "support/primary",
            _route(profile="missing"),
            "llm_model_profile_missing",
        ),
    ],
)
def test_config_rejects_unknown_default_or_profile_refs(
    default_model: str,
    route: LlmModelRoute,
    error_type: str,
) -> None:
    """Default와 route profile은 operator catalog 밖으로 벗어나지 않는다."""
    with pytest.raises(ValidationError) as raised:
        LlmConfig(
            default_model=default_model,
            profiles={"vllm-local": _vllm_profile()},
            models={"support/primary": route},
        )

    assert raised.value.errors()[0]["type"] == error_type


def test_config_rejects_misspelled_nested_environment_field(monkeypatch) -> None:
    """Nested catalog typo는 SDK default로 silent fallback하지 않는다."""
    monkeypatch.setenv("SPAKKY_LLM__DEFAULT_MODEL", "support/primary")
    monkeypatch.setenv(
        "SPAKKY_LLM__PROFILES",
        dumps(
            {
                "vllm-local": {
                    "provider": "vllm",
                    "api": "openai-chat-completions",
                    "base_url": "http://localhost:8000/v1",
                    "base_ulr": "http://attacker.invalid/v1",
                    "openai_dialect": "vllm",
                }
            }
        ),
    )
    monkeypatch.setenv(
        "SPAKKY_LLM__MODELS",
        dumps(
            {
                "support/primary": {
                    "profile": "vllm-local",
                    "model": "default",
                }
            }
        ),
    )

    with pytest.raises(ValidationError) as raised:
        LlmConfig()

    assert raised.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize("field", ["PROFILSE", "DEFAULT_PROFILE"])
def test_config_rejects_unknown_or_legacy_top_level_environment_fields(
    monkeypatch,
    field: str,
) -> None:
    """Top-level typo와 legacy selector 설정은 alias 없이 fail closed 된다."""
    monkeypatch.setenv(f"SPAKKY_LLM__{field}", "legacy")

    with pytest.raises(PydanticCustomError) as raised:
        LlmConfig()

    assert raised.value.type == "llm_environment_field"
