"""Tests for A2A plugin configuration."""

import pytest

from spakky.plugins.a2a.config import (
    DEFAULT_A2A_BASE_URL,
    DEFAULT_A2A_VERSION,
    SPAKKY_A2A_CONFIG_ENV_PREFIX,
    A2AConfig,
)


def test_a2a_config_uses_defaults_when_env_absent() -> None:
    """A2AConfig falls back to default base url and version without env."""
    config = A2AConfig()

    assert config.default_base_url == DEFAULT_A2A_BASE_URL
    assert config.default_version == DEFAULT_A2A_VERSION


def test_a2a_config_loads_base_url_and_version_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A2AConfig reads base url and version from SPAKKY_A2A_* env."""
    monkeypatch.setenv(
        f"{SPAKKY_A2A_CONFIG_ENV_PREFIX}DEFAULT_BASE_URL",
        "https://agents.example.com",
    )
    monkeypatch.setenv(f"{SPAKKY_A2A_CONFIG_ENV_PREFIX}DEFAULT_VERSION", "2.3.4")

    config = A2AConfig()

    assert config.default_base_url == "https://agents.example.com"
    assert config.default_version == "2.3.4"
