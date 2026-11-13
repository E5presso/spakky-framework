"""Configuration for operator-owned OAuth 2.0 client registrations."""

from typing import ClassVar
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

from spakky.plugins.oauth.constants import (
    DEFAULT_OAUTH_AUTHORIZATION_TTL_SECONDS,
    DEFAULT_OAUTH_HTTP_TIMEOUT_SECONDS,
    DEFAULT_OAUTH_REFRESH_LEEWAY_SECONDS,
    SPAKKY_OAUTH_CONFIG_ENV_PREFIX,
)

RESERVED_AUTHORIZATION_PARAMETERS = frozenset(
    {
        "response_type",
        "client_id",
        "redirect_uri",
        "scope",
        "state",
        "nonce",
        "code_challenge",
        "code_challenge_method",
    }
)
_RESERVED_TOKEN_PARAMETERS = frozenset(
    {
        "grant_type",
        "client_id",
        "code",
        "code_verifier",
        "redirect_uri",
        "refresh_token",
    }
)
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class OAuthClientRegistration(BaseModel):
    """One public-client registration at an OAuth 2.0 authorization server."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    authorization_endpoint: str
    token_endpoint: str
    # None means the server offers no revocation; sign-out only clears local tokens.
    revocation_endpoint: str | None = None
    client_id: str = Field(min_length=1)
    scopes: tuple[str, ...] = ()
    authorization_parameters: dict[str, str] = Field(default_factory=dict)
    token_parameters: dict[str, str] = Field(default_factory=dict)

    @field_validator(
        "authorization_endpoint",
        "token_endpoint",
        "revocation_endpoint",
    )
    @classmethod
    def _validate_endpoint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = urlsplit(value.strip())
        secure = parts.scheme == "https"
        loopback = parts.scheme == "http" and parts.hostname in _LOOPBACK_HOSTS
        if parts.hostname is None or parts.fragment != "" or not (secure or loopback):
            raise PydanticCustomError(
                "oauth_endpoint",
                "OAuth endpoints must use https (http on loopback) without a fragment",
            )
        return value.strip()

    @field_validator("client_id")
    @classmethod
    def _validate_client_id(cls, value: str) -> str:
        stripped = value.strip()
        if stripped == "":
            raise PydanticCustomError(
                "oauth_client_id",
                "OAuth client id cannot be blank",
            )
        return stripped

    @field_validator("scopes")
    @classmethod
    def _validate_scopes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(scope.strip() == "" or " " in scope for scope in value):
            raise PydanticCustomError(
                "oauth_scope",
                "OAuth scopes must be non-blank tokens without spaces",
            )
        if len(set(value)) != len(value):
            raise PydanticCustomError(
                "oauth_scope_duplicate",
                "OAuth scopes must be unique",
            )
        return value

    @field_validator("authorization_parameters")
    @classmethod
    def _validate_authorization_parameters(
        cls,
        value: dict[str, str],
    ) -> dict[str, str]:
        if not RESERVED_AUTHORIZATION_PARAMETERS.isdisjoint(value):
            raise PydanticCustomError(
                "oauth_authorization_parameter",
                "Extra authorization parameters cannot override protocol fields",
            )
        return value

    @field_validator("token_parameters")
    @classmethod
    def _validate_token_parameters(cls, value: dict[str, str]) -> dict[str, str]:
        if not _RESERVED_TOKEN_PARAMETERS.isdisjoint(value):
            raise PydanticCustomError(
                "oauth_token_parameter",
                "Extra token parameters cannot override protocol fields",
            )
        return value


@Configuration()
class OAuthConfig(BaseSettings):
    """Named OAuth 2.0 client registrations and token lifetime policy."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_OAUTH_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="forbid",
    )

    clients: dict[str, OAuthClientRegistration] = Field(default_factory=dict)
    """Registrations keyed by the name callers pass to ``OAuthClient``."""

    http_timeout_seconds: float = Field(
        default=DEFAULT_OAUTH_HTTP_TIMEOUT_SECONDS,
        gt=0,
    )
    """Timeout for each token and revocation endpoint request."""

    refresh_leeway_seconds: float = Field(
        default=DEFAULT_OAUTH_REFRESH_LEEWAY_SECONDS,
        ge=0,
    )
    """Refresh an access token this long before it expires."""

    authorization_ttl_seconds: float = Field(
        default=DEFAULT_OAUTH_AUTHORIZATION_TTL_SECONDS,
        gt=0,
    )
    """How long a started authorization waits for its callback."""

    def __init__(self) -> None:
        super().__init__()
