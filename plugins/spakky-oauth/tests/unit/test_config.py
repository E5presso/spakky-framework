"""Configuration tests for OAuth client registrations."""

from json import dumps

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from spakky.plugins.oauth.config import OAuthClientRegistration, OAuthConfig


def _values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "authorization_endpoint": "https://auth.example.test/authorize",
        "token_endpoint": "https://auth.example.test/token",
        "client_id": "my-app",
    }
    values.update(overrides)
    return values


def test_registration_expect_normalized_endpoints_and_defaults() -> None:
    """A minimal registration needs only endpoints and a client id."""
    registration = OAuthClientRegistration.model_validate(
        _values(
            client_id=" my-app ", token_endpoint=" https://auth.example.test/token "
        )
    )

    assert registration.client_id == "my-app"
    assert registration.token_endpoint == "https://auth.example.test/token"
    assert registration.revocation_endpoint is None
    assert registration.scopes == ()
    assert registration.authorization_parameters == {}
    assert registration.token_parameters == {}


def test_registration_on_loopback_http_expect_accepted() -> None:
    """Plain http is allowed only for a loopback authorization server."""
    registration = OAuthClientRegistration.model_validate(
        _values(revocation_endpoint="http://127.0.0.1:9000/revoke")
    )

    assert registration.revocation_endpoint == "http://127.0.0.1:9000/revoke"


@pytest.mark.parametrize(
    ("overrides", "error_type"),
    [
        ({"token_endpoint": "http://auth.example.test/token"}, "oauth_endpoint"),
        ({"authorization_endpoint": "https:///authorize"}, "oauth_endpoint"),
        ({"revocation_endpoint": "ftp://auth.example.test/revoke"}, "oauth_endpoint"),
        (
            {"authorization_endpoint": "https://auth.example.test/authorize#x"},
            "oauth_endpoint",
        ),
        ({"client_id": "  "}, "oauth_client_id"),
        ({"scopes": ["openid", "two words"]}, "oauth_scope"),
        ({"scopes": ["openid", " "]}, "oauth_scope"),
        ({"scopes": ["openid", "openid"]}, "oauth_scope_duplicate"),
        (
            {"authorization_parameters": {"state": "fixed"}},
            "oauth_authorization_parameter",
        ),
        ({"token_parameters": {"code_verifier": "fixed"}}, "oauth_token_parameter"),
        ({"client_secret": "nope"}, "extra_forbidden"),
    ],
)
def test_invalid_registration_expect_validation_error(
    overrides: dict[str, object],
    error_type: str,
) -> None:
    """Insecure endpoints, blank ids, and protocol overrides are rejected."""
    with pytest.raises(ValidationError) as raised:
        OAuthClientRegistration.model_validate(_values(**overrides))

    assert raised.value.errors()[0]["type"] == error_type


def test_config_from_environment_expect_named_clients(monkeypatch: MonkeyPatch) -> None:
    """Operators declare registrations through the SPAKKY_OAUTH__ environment."""
    monkeypatch.setenv(
        "SPAKKY_OAUTH__CLIENTS",
        dumps(
            {"example": _values(scopes=["openid"], token_parameters={"resource": "r"})}
        ),
    )
    monkeypatch.setenv("SPAKKY_OAUTH__REFRESH_LEEWAY_SECONDS", "30")

    config = OAuthConfig()

    assert config.clients["example"].scopes == ("openid",)
    assert config.clients["example"].token_parameters == {"resource": "r"}
    assert config.refresh_leeway_seconds == 30
    assert config.http_timeout_seconds == 20
    assert config.authorization_ttl_seconds == 600


def test_config_without_environment_expect_no_clients(monkeypatch: MonkeyPatch) -> None:
    """With nothing configured there are no registrations to use."""
    monkeypatch.delenv("SPAKKY_OAUTH__CLIENTS", raising=False)

    assert OAuthConfig().clients == {}
