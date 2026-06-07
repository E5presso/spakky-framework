"""OIDC provider-specific errors."""

from typing import final

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyOidcError(AbstractSpakkyFrameworkError):
    """Base class for spakky-oidc provider errors."""

    message = "OIDC bearer authentication failed"


@final
class OidcDiscoveryError(AbstractSpakkyOidcError):
    """Raised when OIDC discovery metadata cannot be loaded or trusted."""

    message = "OIDC discovery metadata is unavailable or invalid"


@final
class OidcJwksError(AbstractSpakkyOidcError):
    """Raised when JWKS keys cannot validate the bearer credential."""

    message = "OIDC JWKS key material is unavailable or invalid"


@final
class OidcCredentialError(AbstractSpakkyOidcError):
    """Raised when the credential carrier is not a usable bearer token."""

    message = "OIDC bearer credential is missing or invalid"


@final
class OidcTokenValidationError(AbstractSpakkyOidcError):
    """Raised when JWT claims or signatures fail OIDC validation."""

    message = "OIDC bearer token validation failed"
