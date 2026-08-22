"""Tests for fallback, resilience, and cache configuration contracts."""

from json import dumps
from math import inf

import pytest
from pydantic import SecretStr, ValidationError

from spakky.plugins.llm.cache import LlmCacheMode
from spakky.plugins.llm.config import (
    LlmConfig,
    LlmModelRoute,
    LlmProfile,
    LlmProviderApi,
)
from spakky.plugins.llm.error import (
    LlmConfigurationError,
    LlmFailureClass,
    LlmRateLimitError,
)
from spakky.plugins.llm.resilience import (
    LlmCircuitBreakerPolicy,
    LlmConcurrencyPolicy,
    LlmResiliencePolicy,
    LlmRetryPolicy,
)


def _profile(
    *,
    max_retries: int = 0,
    resilience: LlmResiliencePolicy | None = None,
) -> LlmProfile:
    return LlmProfile(
        provider="openai",
        api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
        api_key=SecretStr("secret"),
        max_retries=max_retries,
        resilience=resilience or LlmResiliencePolicy(),
    )


def _route(
    *,
    fallbacks: tuple[str, ...] = (),
    fallback_on: frozenset[LlmFailureClass] = frozenset(),
) -> LlmModelRoute:
    return LlmModelRoute(
        profile="profile",
        model="physical",
        fallbacks=fallbacks,
        fallback_on=fallback_on,
    )


def test_config_defaults_expect_no_fallback_retry_limit_circuit_or_cache() -> None:
    """Default catalog snapshot preserves one call and disabled resilience features."""
    config = LlmConfig()
    route = config.models[config.default_model]
    profile = config.profiles[route.profile]

    assert route.fallbacks == ()
    assert route.fallback_on == frozenset()
    assert route.cache.mode is LlmCacheMode.DISABLED
    assert profile.resilience.retry.max_attempts == 1
    assert profile.resilience.concurrency.max_in_flight is None
    assert profile.resilience.rate_limit.requests_per_period is None
    assert profile.resilience.circuit.failure_threshold is None


@pytest.mark.parametrize(
    ("models", "error_type"),
    (
        (
            {
                "primary": _route(
                    fallbacks=("missing",),
                    fallback_on=frozenset({LlmFailureClass.TIMEOUT}),
                )
            },
            "llm_model_route_fallback_missing",
        ),
        (
            {
                "primary": _route(
                    fallbacks=("primary",),
                    fallback_on=frozenset({LlmFailureClass.TIMEOUT}),
                )
            },
            "llm_model_route_fallback_self",
        ),
        (
            {
                "primary": _route(
                    fallbacks=("fallback",),
                    fallback_on=frozenset({LlmFailureClass.TIMEOUT}),
                ),
                "fallback": _route(
                    fallbacks=("primary",),
                    fallback_on=frozenset({LlmFailureClass.TIMEOUT}),
                ),
            },
            "llm_model_route_fallback_cycle",
        ),
    ),
)
def test_catalog_rejects_unknown_self_or_cyclic_fallbacks(
    models: dict[str, LlmModelRoute],
    error_type: str,
) -> None:
    """Fallback graph validation fails before a router can snapshot it."""
    with pytest.raises(ValidationError) as raised:
        LlmConfig(
            default_model="primary", profiles={"profile": _profile()}, models=models
        )

    assert raised.value.errors()[0]["type"] == error_type


def test_route_rejects_duplicate_or_unpaired_fallback_policy() -> None:
    """Ordered refs are unique and require an explicit failure-class allowlist."""
    with pytest.raises(ValidationError) as duplicate:
        _route(
            fallbacks=("fallback", "fallback"),
            fallback_on=frozenset({LlmFailureClass.TIMEOUT}),
        )
    with pytest.raises(ValidationError) as missing_allowlist:
        _route(fallbacks=("fallback",))
    with pytest.raises(ValidationError) as missing_refs:
        _route(fallback_on=frozenset({LlmFailureClass.TIMEOUT}))

    assert duplicate.value.errors()[0]["type"] == ("llm_model_route_fallback_duplicate")
    assert missing_allowlist.value.errors()[0]["type"] == (
        "llm_model_route_fallback_policy"
    )
    assert missing_refs.value.errors()[0]["type"] == ("llm_model_route_fallback_policy")


def test_profile_rejects_simultaneous_sdk_and_orchestration_retry() -> None:
    """Retry ownership is singular so attempt multiplication cannot be silent."""
    retry = LlmRetryPolicy(
        max_attempts=2,
        failure_classes=frozenset({LlmFailureClass.TIMEOUT}),
    )

    with pytest.raises(ValidationError) as raised:
        _profile(
            max_retries=1,
            resilience=LlmResiliencePolicy(retry=retry),
        )

    assert raised.value.errors()[0]["type"] == "llm_retry_owner"


@pytest.mark.parametrize("retry_after", (-1.0, inf))
def test_typed_retry_after_expect_finite_nonnegative_value(retry_after: float) -> None:
    """Malformed provider Retry-After metadata fails through plugin configuration."""
    with pytest.raises(LlmConfigurationError):
        LlmRateLimitError(retry_after_seconds=retry_after)


@pytest.mark.parametrize(
    "factory",
    (
        lambda: LlmRetryPolicy(max_attempts=2),
        lambda: LlmRetryPolicy(backoff_seconds=2.0, max_backoff_seconds=1.0),
        lambda: LlmConcurrencyPolicy(queue_timeout_seconds=1.0),
        lambda: LlmCircuitBreakerPolicy(
            failure_threshold=1,
            failure_classes=frozenset(),
        ),
    ),
)
def test_resilience_policy_rejects_ambiguous_enabled_settings(factory) -> None:
    """Enabled controls require every semantic boundary to be explicit."""
    with pytest.raises(ValidationError):
        factory()


def test_environment_catalog_loads_fallback_resilience_and_cache(monkeypatch) -> None:
    """Nested JSON environment config preserves the complete operator policy snapshot."""
    monkeypatch.setenv("SPAKKY_LLM__DEFAULT_MODEL", "primary")
    monkeypatch.setenv(
        "SPAKKY_LLM__PROFILES",
        dumps(
            {
                "profile": {
                    "provider": "openai",
                    "api": "openai-chat-completions",
                    "api_key": "secret",
                    "resilience": {
                        "retry": {
                            "max_attempts": 2,
                            "failure_classes": ["timeout"],
                        },
                        "concurrency": {"max_in_flight": 3},
                        "circuit": {"failure_threshold": 2},
                    },
                }
            }
        ),
    )
    monkeypatch.setenv(
        "SPAKKY_LLM__MODELS",
        dumps(
            {
                "primary": {
                    "profile": "profile",
                    "model": "physical-primary",
                    "fallbacks": ["fallback"],
                    "fallback_on": ["timeout"],
                    "cache": {"mode": "semantic", "ttl_seconds": 60},
                },
                "fallback": {
                    "profile": "profile",
                    "model": "physical-fallback",
                },
            }
        ),
    )

    config = LlmConfig()

    assert config.models["primary"].fallbacks == ("fallback",)
    assert config.models["primary"].fallback_on == frozenset({LlmFailureClass.TIMEOUT})
    assert config.models["primary"].cache.mode is LlmCacheMode.SEMANTIC
    assert config.profiles["profile"].resilience.retry.max_attempts == 2
    assert config.profiles["profile"].resilience.concurrency.max_in_flight == 3
    assert config.profiles["profile"].resilience.circuit.failure_threshold == 2
