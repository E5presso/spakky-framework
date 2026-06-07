"""OIDC bearer authentication provider."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import final, override, cast
from urllib.error import URLError
from urllib.request import urlopen
import json

import jwt
from jwt import PyJWK, PyJWTError

from spakky.auth import (
    AuthCapability,
    AuthClaim,
    AuthClaimValue,
    AuthContext,
    AuthInvocation,
    AuthProviderContribution,
    AuthSubject,
    AuthorizationDecision,
    AuthorizationReasonCode,
    CredentialCarrier,
    CredentialCarrierKind,
    IAuthenticationProvider,
)
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.oidc.error import (
    AbstractSpakkyOidcError,
    OidcCredentialError,
    OidcDiscoveryError,
    OidcJwksError,
    OidcTokenValidationError,
)

OIDC_AUTH_PROVIDER_ID = "provider:spakky-oidc"
"""Stable auth provider id advertised by spakky-oidc."""

DEFAULT_RETAINED_CLAIMS = (
    "sub",
    "iss",
    "aud",
    "azp",
    "email",
    "name",
    "preferred_username",
)
"""Safe claim names retained in AuthContext; raw token material is excluded."""

JsonObject = dict[str, object]
JsonFetcher = Callable[[str], JsonObject]


def fetch_json_document(url: str) -> JsonObject:
    """Fetch a JSON object from an OIDC metadata URL."""
    try:
        with urlopen(url, timeout=5) as response:
            payload = json.load(response)
    except (OSError, URLError, json.JSONDecodeError) as exc:
        raise OidcDiscoveryError() from exc
    if isinstance(payload, dict):
        return _string_keyed_dict(payload)
    raise OidcDiscoveryError()


@dataclass(frozen=True, slots=True, kw_only=True)
class OidcProviderConfig:
    """Runtime config for OIDC bearer authentication."""

    issuer: str
    """Expected issuer and base URL for discovery when discovery_url is omitted."""

    audience: str | tuple[str, ...]
    """Accepted audience value or values."""

    client_id: str | None = None
    """Expected authorized party (`azp`) when the token carries it."""

    discovery_url: str | None = None
    """Explicit OIDC discovery URL; defaults to issuer/.well-known/openid-configuration."""

    algorithm: str = "RS256"
    """Expected JWT signing algorithm."""

    clock_skew: timedelta = timedelta(seconds=60)
    """Allowed exp/nbf/iat clock skew."""

    retained_claim_names: tuple[str, ...] = DEFAULT_RETAINED_CLAIMS
    """JWT claim names safe to retain on AuthContext."""

    roles_claim: str = "roles"
    """Claim containing role refs as a string or string array."""

    scopes_claim: str = "scope"
    """Claim containing scope refs as a space-delimited string or string array."""

    tenant_claim: str | None = "tenant"
    """Optional claim containing the tenant canonical ref."""

    display_name_claim: str | None = "name"
    """Optional claim containing a human-readable subject label."""

    json_fetcher: JsonFetcher = fetch_json_document
    """Fetches discovery and JWKS JSON; injectable for deterministic tests."""

    provider_available: bool = True
    """Whether provider dependencies are usable at runtime."""


@dataclass(frozen=True, slots=True, kw_only=True)
class OidcAuthenticationResult:
    """Decision plus optional AuthContext produced by bearer authentication."""

    decision: AuthorizationDecision
    """ALLOW, CHALLENGE, or ERROR decision for the authentication attempt."""

    auth_context: AuthContext | None = None
    """Authenticated context when decision is ALLOW."""


@dataclass(frozen=True, slots=True, kw_only=True)
class OidcDiscoveryMetadata:
    """Trusted subset of OIDC discovery metadata."""

    issuer: str
    """Issuer reported by the discovery document."""

    jwks_uri: str
    """JWKS endpoint used to select token verification keys."""


@Pod()
@final
class OidcAuthenticationProvider(IAuthenticationProvider):
    """OIDC JWT bearer implementation of the provider-neutral auth port."""

    _config: OidcProviderConfig

    def __init__(
        self,
        config: OidcProviderConfig = OidcProviderConfig(
            issuer="https://issuer.example.test",
            audience="spakky",
        ),
    ) -> None:
        self._config = config

    @override
    def authenticate(
        self,
        credential: CredentialCarrier,
        invocation: AuthInvocation,
    ) -> AuthContext:
        """Authenticate an OIDC bearer credential and return AuthContext."""
        if not self._config.provider_available:
            raise OidcDiscoveryError()
        token = self._bearer_token(credential)
        metadata = self._discovery_metadata()
        jwk = self._matching_jwk(token, metadata.jwks_uri)
        claims = self._verified_claims(token, jwk, metadata.issuer)
        return self._auth_context_from_claims(claims)

    def authenticate_result(
        self,
        credential: CredentialCarrier,
        invocation: AuthInvocation,
    ) -> OidcAuthenticationResult:
        """Authenticate a bearer token and map failures to auth decisions."""
        try:
            auth_context = self.authenticate(credential, invocation)
        except OidcCredentialError:
            return OidcAuthenticationResult(
                decision=AuthorizationDecision.challenge(
                    AuthorizationReasonCode.MISSING_CREDENTIAL
                )
            )
        except OidcTokenValidationError:
            return OidcAuthenticationResult(
                decision=AuthorizationDecision.challenge(
                    AuthorizationReasonCode.INVALID_CREDENTIAL
                )
            )
        except OidcJwksError:
            return OidcAuthenticationResult(
                decision=AuthorizationDecision.challenge(
                    AuthorizationReasonCode.INVALID_CREDENTIAL
                )
            )
        except OidcDiscoveryError:
            return OidcAuthenticationResult(
                decision=AuthorizationDecision.error(
                    AuthorizationReasonCode.VERIFICATION_PROVIDER_UNAVAILABLE
                )
            )
        return OidcAuthenticationResult(
            decision=AuthorizationDecision.allow(),
            auth_context=auth_context,
        )

    def _bearer_token(self, credential: CredentialCarrier) -> str:
        if credential.kind is not CredentialCarrierKind.BEARER_TOKEN:
            raise OidcCredentialError()
        if credential.material == "":
            raise OidcCredentialError()
        if credential.scheme is not None and credential.scheme.lower() != "bearer":
            raise OidcCredentialError()
        return credential.material

    def _discovery_metadata(self) -> OidcDiscoveryMetadata:
        document = self._config.json_fetcher(self._discovery_url())
        issuer = _required_string(document, "issuer", OidcDiscoveryError)
        jwks_uri = _required_string(document, "jwks_uri", OidcDiscoveryError)
        if issuer != self._config.issuer:
            raise OidcDiscoveryError()
        return OidcDiscoveryMetadata(issuer=issuer, jwks_uri=jwks_uri)

    def _discovery_url(self) -> str:
        if self._config.discovery_url is not None:
            return self._config.discovery_url
        return f"{self._config.issuer.rstrip('/')}/.well-known/openid-configuration"

    def _matching_jwk(self, token: str, jwks_uri: str) -> JsonObject:
        header = self._token_header(token)
        algorithm = _required_string(header, "alg", OidcTokenValidationError)
        if algorithm != self._config.algorithm:
            raise OidcTokenValidationError()
        key_id = _required_string(header, "kid", OidcTokenValidationError)
        jwks = self._config.json_fetcher(jwks_uri)
        keys = jwks.get("keys")
        if not isinstance(keys, list):
            raise OidcJwksError()
        for key in keys:
            if not isinstance(key, dict):
                raise OidcJwksError()
            jwk = _string_keyed_dict(key)
            if jwk.get("kid") == key_id:
                return jwk
        raise OidcJwksError()

    def _token_header(self, token: str) -> JsonObject:
        try:
            return _string_keyed_dict(
                cast(dict[object, object], jwt.get_unverified_header(token))
            )
        except PyJWTError as exc:
            raise OidcTokenValidationError() from exc

    def _verified_claims(
        self,
        token: str,
        jwk: JsonObject,
        issuer: str,
    ) -> JsonObject:
        try:
            signing_key = PyJWK.from_dict(jwk).key
            payload = jwt.decode(
                token,
                key=signing_key,
                algorithms=(self._config.algorithm,),
                audience=self._config.audience,
                issuer=issuer,
                leeway=self._config.clock_skew,
                options={"require": ["sub", "iss", "aud", "exp", "iat"]},
            )
        except PyJWTError as exc:
            raise OidcTokenValidationError() from exc
        claims = _string_keyed_dict(cast(dict[object, object], payload))
        self._validate_authorized_party(claims)
        return claims

    def _validate_authorized_party(self, claims: JsonObject) -> None:
        if self._config.client_id is None:
            return
        audiences = self._audiences(claims)
        azp = claims.get("azp")
        if len(audiences) > 1 and azp is None:
            raise OidcTokenValidationError()
        if azp is not None and azp != self._config.client_id:
            raise OidcTokenValidationError()

    def _audiences(self, claims: JsonObject) -> tuple[str, ...]:
        audience = claims.get("aud")
        if isinstance(audience, str):
            return (audience,)
        if isinstance(audience, list | tuple):
            values: list[str] = []
            for item in audience:
                if not isinstance(item, str):
                    raise OidcTokenValidationError()
                values.append(item)
            return tuple(values)
        raise OidcTokenValidationError()

    def _auth_context_from_claims(self, claims: JsonObject) -> AuthContext:
        subject = AuthSubject(
            id=_required_string(claims, "sub", OidcTokenValidationError),
            display_name=self._optional_string_claim(
                claims,
                self._config.display_name_claim,
            ),
        )
        return AuthContext(
            subject=subject,
            issuer=_required_string(claims, "iss", OidcTokenValidationError),
            tenant=self._optional_string_claim(claims, self._config.tenant_claim),
            roles=self._string_tuple_claim(claims, self._config.roles_claim),
            scopes=self._scope_tuple_claim(claims, self._config.scopes_claim),
            claims=self._retained_claims(claims),
        )

    def _optional_string_claim(
        self,
        claims: JsonObject,
        claim_name: str | None,
    ) -> str | None:
        if claim_name is None:
            return None
        value = claims.get(claim_name)
        if value is None:
            return None
        if isinstance(value, str):
            return value
        raise OidcTokenValidationError()

    def _string_tuple_claim(
        self,
        claims: JsonObject,
        claim_name: str,
    ) -> tuple[str, ...]:
        value = claims.get(claim_name)
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        if isinstance(value, list | tuple):
            values: list[str] = []
            for item in value:
                if not isinstance(item, str):
                    raise OidcTokenValidationError()
                values.append(item)
            return tuple(values)
        raise OidcTokenValidationError()

    def _scope_tuple_claim(
        self,
        claims: JsonObject,
        claim_name: str,
    ) -> tuple[str, ...]:
        value = claims.get(claim_name)
        if value is None:
            return ()
        if isinstance(value, str):
            return tuple(scope for scope in value.split(" ") if scope != "")
        return self._string_tuple_claim(claims, claim_name)

    def _retained_claims(self, claims: JsonObject) -> tuple[AuthClaim, ...]:
        retained: list[AuthClaim] = []
        for name in sorted(self._config.retained_claim_names):
            if name in claims:
                retained.append(
                    AuthClaim(
                        name=name,
                        value=self._claim_value(claims[name]),
                    )
                )
        return tuple(retained)

    def _claim_value(self, value: object) -> AuthClaimValue:
        if value is None:
            return None
        if isinstance(value, str | int | float | bool):
            return value
        raise OidcTokenValidationError()


def _required_string(
    payload: JsonObject,
    key: str,
    error_type: type[AbstractSpakkyOidcError],
) -> str:
    value = payload.get(key)
    if isinstance(value, str) and value != "":
        return value
    raise error_type()


def _string_keyed_dict(payload: dict[object, object]) -> JsonObject:
    result: JsonObject = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise OidcTokenValidationError()
        result[key] = value
    return result


@Pod(name="spakky_oidc_auth_provider_contribution")
def oidc_auth_provider_contribution() -> AuthProviderContribution:
    """Return the auth capabilities contributed by spakky-oidc."""
    return AuthProviderContribution(
        provider_id=OIDC_AUTH_PROVIDER_ID,
        capabilities=frozenset({AuthCapability.AUTHENTICATION}),
    )
