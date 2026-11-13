"""Errors raised by the OAuth 2.0 client plugin."""

from abc import ABC
from typing import final

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyOAuthError(AbstractSpakkyFrameworkError, ABC):
    """Base class for spakky-oauth client errors."""

    message = "OAuth client operation failed"


@final
class OAuthClientNotConfiguredError(AbstractSpakkyOAuthError):
    """Raised when a caller names a client registration that does not exist."""

    message = "OAuth client registration is not configured"


@final
class OAuthAuthorizationRequestError(AbstractSpakkyOAuthError):
    """Raised when a caller's per-request authorization arguments are invalid."""

    message = "OAuth authorization request arguments are invalid"


@final
class OAuthAuthorizationStateError(AbstractSpakkyOAuthError):
    """Raised when a callback state is unknown, already used, or expired."""

    message = "OAuth authorization state is unknown or expired"


@final
class OAuthAuthorizationRequiredError(AbstractSpakkyOAuthError):
    """Raised when the subject must sign in again to obtain a usable token."""

    message = "OAuth authorization is required for the subject"


@final
class OAuthTokenEndpointError(AbstractSpakkyOAuthError):
    """Raised when the token endpoint rejects a request for a non-grant reason."""

    message = "OAuth token endpoint rejected the request"


@final
class OAuthTokenResponseError(AbstractSpakkyOAuthError):
    """Raised when a token endpoint response is not a usable bearer token set."""

    message = "OAuth token endpoint response is invalid"


@final
class OAuthTransportError(AbstractSpakkyOAuthError):
    """Raised when the authorization server cannot be reached."""

    message = "OAuth authorization server is unreachable"


@final
class OAuthRevocationError(AbstractSpakkyOAuthError):
    """Raised when local tokens were removed but the server did not confirm it."""

    message = "OAuth token revocation was not confirmed by the server"
