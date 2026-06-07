"""OIDC bearer authentication provider plugin public API."""

from spakky.core.application.plugin import Plugin
from spakky.plugins.oidc.error import (
    AbstractSpakkyOidcError,
    OidcCredentialError,
    OidcDiscoveryError,
    OidcJwksError,
    OidcTokenValidationError,
)
from spakky.plugins.oidc.provider import (
    OIDC_AUTH_PROVIDER_ID,
    DEFAULT_RETAINED_CLAIMS,
    OidcAuthenticationProvider,
    OidcAuthenticationResult,
    OidcDiscoveryMetadata,
    OidcProviderConfig,
    fetch_json_document,
    oidc_auth_provider_contribution,
)

PLUGIN_NAME = Plugin(name="spakky-oidc")

__all__ = [
    "PLUGIN_NAME",
    "AbstractSpakkyOidcError",
    "DEFAULT_RETAINED_CLAIMS",
    "OIDC_AUTH_PROVIDER_ID",
    "OidcAuthenticationProvider",
    "OidcAuthenticationResult",
    "OidcCredentialError",
    "OidcDiscoveryError",
    "OidcDiscoveryMetadata",
    "OidcJwksError",
    "OidcProviderConfig",
    "OidcTokenValidationError",
    "fetch_json_document",
    "oidc_auth_provider_contribution",
]
