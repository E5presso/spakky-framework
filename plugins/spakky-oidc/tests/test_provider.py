from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from importlib.metadata import entry_points
from pathlib import Path
from urllib.error import URLError

import jwt
import pytest
import spakky.auth
import spakky.plugins.oidc
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.utils import base64url_encode
from spakky.auth import (
    AuthCapability,
    AuthInvocation,
    AuthProviderContribution,
    AuthorizationDecisionState,
    AuthorizationReasonCode,
    CredentialCarrier,
    CredentialCarrierKind,
    CredentialCarrierLocation,
)
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.plugins.oidc.error import (
    OidcCredentialError,
    OidcDiscoveryError,
    OidcJwksError,
    OidcTokenValidationError,
)
from spakky.plugins.oidc.provider import (
    OIDC_AUTH_PROVIDER_ID,
    OidcAuthenticationProvider,
    OidcProviderConfig,
    _string_keyed_dict,
    fetch_json_document,
    oidc_auth_provider_contribution,
)

ISSUER = "https://issuer.example.test"
AUDIENCE = "api://spakky"
CLIENT_ID = "spakky-client"
KID = "key-1"


def _private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _int_to_base64url(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    return base64url_encode(value.to_bytes(length, "big")).decode("ascii")


def _public_jwk(key: rsa.RSAPrivateKey, kid: str = KID) -> dict[str, object]:
    numbers = key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "kid": kid,
        "alg": "RS256",
        "n": _int_to_base64url(numbers.n),
        "e": _int_to_base64url(numbers.e),
    }


def _claims(now: datetime) -> dict[str, object]:
    return {
        "iss": ISSUER,
        "sub": "subject-1",
        "aud": AUDIENCE,
        "azp": CLIENT_ID,
        "exp": now + timedelta(minutes=5),
        "nbf": now - timedelta(seconds=30),
        "iat": now,
        "scope": "documents:read documents:write",
        "roles": ["role:admin", "role:writer"],
        "tenant": "tenant-1",
        "name": "Subject One",
        "email": "subject@example.test",
        "preferred_username": None,
        "raw_token": "must-not-retain",
    }


def _token(
    key: rsa.RSAPrivateKey,
    claims: dict[str, object],
    kid: str = KID,
    algorithm: str = "RS256",
) -> str:
    return jwt.encode(claims, key=key, algorithm=algorithm, headers={"kid": kid})


def _carrier(token: str, scheme: str | None = "Bearer") -> CredentialCarrier:
    return CredentialCarrier(
        kind=CredentialCarrierKind.BEARER_TOKEN,
        location=CredentialCarrierLocation.AUTHORIZATION_HEADER,
        material=token,
        name="Authorization",
        scheme=scheme,
    )


def _invocation() -> AuthInvocation:
    return AuthInvocation(boundary="http", operation="GET /documents")


def _fetcher(jwk: dict[str, object]) -> Callable[[str], dict[str, object]]:
    def fetch(url: str) -> dict[str, object]:
        if url == f"{ISSUER}/.well-known/openid-configuration":
            return {"issuer": ISSUER, "jwks_uri": f"{ISSUER}/jwks.json"}
        if url == f"{ISSUER}/jwks.json":
            return {"keys": [jwk]}
        return {}

    return fetch


def _config(**overrides: object) -> OidcProviderConfig:
    return OidcProviderConfig().model_copy(update=overrides)


def _provider(jwk: dict[str, object]) -> OidcAuthenticationProvider:
    return OidcAuthenticationProvider(
        config=_config(
            issuer=ISSUER,
            audience=AUDIENCE,
            client_id=CLIENT_ID,
            json_fetcher=_fetcher(jwk),
        )
    )


def test_oidc_contribution_entry_point_is_declared() -> None:
    contribution_entry_points = entry_points(group="spakky.contributions.spakky.auth")

    assert any(
        entry_point.name == "spakky-oidc"
        and entry_point.value == "spakky.plugins.oidc.contributions.auth:initialize"
        for entry_point in contribution_entry_points
    )


def test_oidc_auth_provider_contribution_declares_authentication() -> None:
    contribution = oidc_auth_provider_contribution()

    assert contribution.provider_id == OIDC_AUTH_PROVIDER_ID
    assert contribution.capabilities == frozenset({AuthCapability.AUTHENTICATION})


def test_load_plugins_with_auth_and_oidc_registers_provider_contribution() -> None:
    app = SpakkyApplication(ApplicationContext()).load_plugins(
        include={spakky.auth.PLUGIN_NAME, spakky.plugins.oidc.PLUGIN_NAME}
    )
    contributions = app.container.find(
        lambda pod: pod.type_ is AuthProviderContribution
    )

    assert any(
        isinstance(contribution, AuthProviderContribution)
        and contribution.provider_id == OIDC_AUTH_PROVIDER_ID
        for contribution in contributions
    )


def test_load_plugins_with_oidc_expect_binds_authentication_provider() -> None:
    """load_plugins()가 OIDC provider를 auth port에 binding하는지 검증한다."""
    app = SpakkyApplication(ApplicationContext()).load_plugins(
        include={spakky.plugins.oidc.PLUGIN_NAME}
    )

    provider = app.container.get(spakky.auth.IAuthenticationProvider)

    assert isinstance(provider, OidcAuthenticationProvider)


def test_valid_oidc_bearer_maps_to_auth_context_without_raw_token() -> None:
    key = _private_key()
    now = datetime.now(UTC)
    token = _token(key, _claims(now))
    provider = _provider(_public_jwk(key))

    auth_context = provider.authenticate(_carrier(token), _invocation())

    assert auth_context.subject.id == "subject-1"
    assert auth_context.subject.display_name == "Subject One"
    assert auth_context.issuer == ISSUER
    assert auth_context.tenant == "tenant-1"
    assert auth_context.roles == ("role:admin", "role:writer")
    assert auth_context.scopes == ("documents:read", "documents:write")
    assert auth_context.credential_carrier is None
    claim_names = tuple(claim.name for claim in auth_context.claims)
    assert "raw_token" not in claim_names
    assert token not in tuple(str(claim.value) for claim in auth_context.claims)
    assert auth_context.metadata == ()


def test_valid_multi_audience_with_matching_azp_authenticates_and_retains_aud() -> None:
    key = _private_key()
    claims = _claims(datetime.now(UTC))
    claims["aud"] = [AUDIENCE, "api://other"]
    claims["azp"] = CLIENT_ID
    token = _token(key, claims)
    provider = _provider(_public_jwk(key))

    result = provider.authenticate_result(_carrier(token), _invocation())

    assert result.decision.state == AuthorizationDecisionState.ALLOW
    assert result.auth_context is not None
    retained_claims = {claim.name: claim.value for claim in result.auth_context.claims}
    assert retained_claims["aud"] == '["api://spakky","api://other"]'
    assert retained_claims["azp"] == CLIENT_ID


def test_custom_discovery_url_and_optional_azp_client_are_supported() -> None:
    key = _private_key()
    claims = _claims(datetime.now(UTC))
    claims["tenant"] = None
    token = _token(key, claims)

    def fetch(url: str) -> dict[str, object]:
        if url == "https://metadata.example.test/openid-configuration":
            return {"issuer": ISSUER, "jwks_uri": f"{ISSUER}/jwks.json"}
        if url == f"{ISSUER}/jwks.json":
            return {"keys": [_public_jwk(key)]}
        return {}

    provider = OidcAuthenticationProvider(
        config=_config(
            issuer=ISSUER,
            audience=AUDIENCE,
            client_id=None,
            discovery_url="https://metadata.example.test/openid-configuration",
            json_fetcher=fetch,
        )
    )

    auth_context = provider.authenticate(_carrier(token), _invocation())

    assert auth_context.subject.id == "subject-1"
    assert auth_context.tenant is None


def test_authenticate_result_returns_allow_with_auth_context() -> None:
    key = _private_key()
    token = _token(key, _claims(datetime.now(UTC)))
    provider = _provider(_public_jwk(key))

    result = provider.authenticate_result(_carrier(token), _invocation())

    assert result.decision.state == AuthorizationDecisionState.ALLOW
    assert result.auth_context is not None


def test_missing_or_wrong_credential_maps_to_challenge() -> None:
    provider = _provider(_public_jwk(_private_key()))
    credential = CredentialCarrier(
        kind=CredentialCarrierKind.API_KEY,
        location=CredentialCarrierLocation.HEADER,
        material="secret",
    )

    with pytest.raises(OidcCredentialError):
        provider.authenticate(credential, _invocation())

    result = provider.authenticate_result(credential, _invocation())
    assert result.decision.state == AuthorizationDecisionState.CHALLENGE
    assert result.decision.reason_code == AuthorizationReasonCode.MISSING_CREDENTIAL


@pytest.mark.parametrize(
    ("material", "scheme"),
    [("", "Bearer"), ("token", "Basic")],
)
def test_unusable_bearer_carrier_raises(material: str, scheme: str) -> None:
    provider = _provider(_public_jwk(_private_key()))

    with pytest.raises(OidcCredentialError):
        provider.authenticate(_carrier(material, scheme=scheme), _invocation())


def test_provider_unavailable_maps_to_error() -> None:
    provider = OidcAuthenticationProvider(
        config=_config(
            issuer=ISSUER,
            audience=AUDIENCE,
            provider_available=False,
        )
    )

    result = provider.authenticate_result(_carrier("token"), _invocation())

    assert result.decision.state == AuthorizationDecisionState.ERROR
    assert result.decision.reason_code == (
        AuthorizationReasonCode.VERIFICATION_PROVIDER_UNAVAILABLE
    )


def test_discovery_issuer_mismatch_maps_to_provider_unavailable() -> None:
    def fetch(url: str) -> dict[str, object]:
        return {"issuer": "https://other.example.test", "jwks_uri": f"{ISSUER}/jwks"}

    provider = OidcAuthenticationProvider(
        config=_config(
            issuer=ISSUER,
            audience=AUDIENCE,
            json_fetcher=fetch,
        )
    )

    result = provider.authenticate_result(_carrier("token"), _invocation())

    assert result.decision.state == AuthorizationDecisionState.ERROR


def test_jwks_without_matching_kid_maps_to_invalid_credential() -> None:
    key = _private_key()
    token = _token(key, _claims(datetime.now(UTC)), kid="missing")
    provider = _provider(_public_jwk(key))

    with pytest.raises(OidcJwksError):
        provider.authenticate(_carrier(token), _invocation())

    result = provider.authenticate_result(_carrier(token), _invocation())
    assert result.decision.reason_code == AuthorizationReasonCode.INVALID_CREDENTIAL


def test_invalid_token_signature_maps_to_invalid_credential() -> None:
    signing_key = _private_key()
    verification_key = _private_key()
    token = _token(signing_key, _claims(datetime.now(UTC)))
    provider = _provider(_public_jwk(verification_key))

    with pytest.raises(OidcTokenValidationError):
        provider.authenticate(_carrier(token), _invocation())

    result = provider.authenticate_result(_carrier(token), _invocation())
    assert result.decision.reason_code == AuthorizationReasonCode.INVALID_CREDENTIAL


def test_invalid_audience_issuer_exp_nbf_and_iat_are_rejected() -> None:
    key = _private_key()
    provider = _provider(_public_jwk(key))
    now = datetime.now(UTC)
    invalid_claim_sets = []
    wrong_audience = _claims(now)
    wrong_audience["aud"] = "api://other"
    invalid_claim_sets.append(wrong_audience)
    expired = _claims(now)
    expired["exp"] = now - timedelta(minutes=5)
    invalid_claim_sets.append(expired)
    immature = _claims(now)
    immature["nbf"] = now + timedelta(minutes=5)
    invalid_claim_sets.append(immature)
    future_issued = _claims(now)
    future_issued["iat"] = now + timedelta(minutes=5)
    invalid_claim_sets.append(future_issued)
    wrong_issuer = _claims(now)
    wrong_issuer["iss"] = "https://issuer.other.test"
    invalid_claim_sets.append(wrong_issuer)

    for claims in invalid_claim_sets:
        result = provider.authenticate_result(
            _carrier(_token(key, claims)), _invocation()
        )
        assert result.decision.reason_code == AuthorizationReasonCode.INVALID_CREDENTIAL


def test_azp_is_required_for_multi_audience_and_must_match_client_id() -> None:
    key = _private_key()
    provider = _provider(_public_jwk(key))
    now = datetime.now(UTC)
    missing_azp = _claims(now)
    missing_azp["aud"] = [AUDIENCE, "api://other"]
    del missing_azp["azp"]
    wrong_azp = _claims(now)
    wrong_azp["azp"] = "other-client"

    for claims in (missing_azp, wrong_azp):
        result = provider.authenticate_result(
            _carrier(_token(key, claims)), _invocation()
        )
        assert result.decision.reason_code == AuthorizationReasonCode.INVALID_CREDENTIAL


def test_custom_claim_mapping_supports_string_roles_and_scope_arrays() -> None:
    key = _private_key()
    now = datetime.now(UTC)
    claims = _claims(now)
    claims["groups"] = "role:reader"
    claims["scp"] = ["openid", "profile"]
    claims["tenant_id"] = "tenant-2"
    provider = OidcAuthenticationProvider(
        config=_config(
            issuer=ISSUER,
            audience=AUDIENCE,
            client_id=CLIENT_ID,
            json_fetcher=_fetcher(_public_jwk(key)),
            roles_claim="groups",
            scopes_claim="scp",
            tenant_claim="tenant_id",
            display_name_claim=None,
            retained_claim_names=("sub",),
        )
    )

    auth_context = provider.authenticate(_carrier(_token(key, claims)), _invocation())

    assert auth_context.subject.display_name is None
    assert auth_context.roles == ("role:reader",)
    assert auth_context.scopes == ("openid", "profile")
    assert auth_context.tenant == "tenant-2"
    assert auth_context.claims[0].name == "sub"


@pytest.mark.parametrize(
    "claim_patch",
    [
        {"roles": ["ok", 1]},
        {"scope": ["ok", 1]},
        {"tenant": 42},
        {"aud": [AUDIENCE, 1]},
        {"email": {"nested": "value"}},
    ],
)
def test_invalid_claim_shapes_are_rejected(claim_patch: dict[str, object]) -> None:
    key = _private_key()
    claims = _claims(datetime.now(UTC))
    claims.update(claim_patch)
    provider = _provider(_public_jwk(key))

    result = provider.authenticate_result(_carrier(_token(key, claims)), _invocation())

    assert result.decision.reason_code == AuthorizationReasonCode.INVALID_CREDENTIAL


@pytest.mark.parametrize("audience", [[AUDIENCE, 1], 42])
def test_retained_audience_claim_rejects_non_string_shapes(audience: object) -> None:
    provider = _provider(_public_jwk(_private_key()))

    with pytest.raises(OidcTokenValidationError):
        provider._audience_claim_value(audience)


def test_jwks_shape_and_header_validation_fail_fast() -> None:
    key = _private_key()
    token = _token(key, _claims(datetime.now(UTC)))

    def fetch_bad_keys(url: str) -> dict[str, object]:
        if url.endswith("openid-configuration"):
            return {"issuer": ISSUER, "jwks_uri": f"{ISSUER}/jwks.json"}
        return {"keys": ["not-a-key"]}

    provider = OidcAuthenticationProvider(
        config=_config(
            issuer=ISSUER,
            audience=AUDIENCE,
            json_fetcher=fetch_bad_keys,
        )
    )

    with pytest.raises(OidcJwksError):
        provider.authenticate(_carrier(token), _invocation())

    def fetch_no_keys(url: str) -> dict[str, object]:
        if url.endswith("openid-configuration"):
            return {"issuer": ISSUER, "jwks_uri": f"{ISSUER}/jwks.json"}
        return {"keys": "not-a-list"}

    provider_without_keys = OidcAuthenticationProvider(
        config=_config(
            issuer=ISSUER,
            audience=AUDIENCE,
            json_fetcher=fetch_no_keys,
        )
    )
    with pytest.raises(OidcJwksError):
        provider_without_keys.authenticate(_carrier(token), _invocation())

    hs_token = jwt.encode(_claims(datetime.now(UTC)), key="secret", algorithm="HS256")
    with pytest.raises(OidcTokenValidationError):
        provider.authenticate(_carrier(hs_token), _invocation())

    with pytest.raises(OidcTokenValidationError):
        provider.authenticate(_carrier("not-a-jwt"), _invocation())


def test_missing_discovery_fields_and_non_string_dict_keys_are_rejected() -> None:
    provider = OidcAuthenticationProvider(
        config=_config(
            issuer=ISSUER,
            audience=AUDIENCE,
            json_fetcher=lambda url: {"issuer": ISSUER},
        )
    )

    with pytest.raises(OidcDiscoveryError):
        provider.authenticate(_carrier("token"), _invocation())

    with pytest.raises(OidcTokenValidationError):
        _string_keyed_dict({1: "value"})


def test_fetch_json_document_maps_network_and_non_object_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_urlopen(url: str, timeout: int) -> object:
        raise URLError("offline")

    monkeypatch.setattr("spakky.plugins.oidc.provider.urlopen", failing_urlopen)
    with pytest.raises(OidcDiscoveryError):
        fetch_json_document(
            "https://issuer.example.test/.well-known/openid-configuration"
        )

    class ObjectResponse:
        def __enter__(self) -> "ObjectResponse":
            return self

        def __exit__(
            self,
            exc_type: object,
            exc_value: object,
            traceback: object,
        ) -> None:
            return None

        def read(self) -> bytes:
            return b'{"issuer":"https://issuer.example.test"}'

    def object_urlopen(url: str, timeout: int) -> ObjectResponse:
        return ObjectResponse()

    monkeypatch.setattr("spakky.plugins.oidc.provider.urlopen", object_urlopen)
    assert fetch_json_document(
        "https://issuer.example.test/.well-known/openid-configuration"
    ) == {"issuer": "https://issuer.example.test"}

    class TextResponse:
        def __enter__(self) -> "TextResponse":
            return self

        def __exit__(
            self,
            exc_type: object,
            exc_value: object,
            traceback: object,
        ) -> None:
            return None

        def read(self) -> bytes:
            return b"[]"

    def text_urlopen(url: str, timeout: int) -> TextResponse:
        return TextResponse()

    monkeypatch.setattr("spakky.plugins.oidc.provider.urlopen", text_urlopen)
    with pytest.raises(OidcDiscoveryError):
        fetch_json_document(
            "https://issuer.example.test/.well-known/openid-configuration"
        )


def test_browser_route_symbols_are_not_present() -> None:
    source_root = Path("src/spakky/plugins/oidc")
    source_text = "\n".join(path.read_text() for path in source_root.rglob("*.py"))

    assert "callback" not in source_text
    assert "logout" not in source_text
    assert "session" not in source_text
    assert "refresh" not in source_text
    assert "login" not in source_text
