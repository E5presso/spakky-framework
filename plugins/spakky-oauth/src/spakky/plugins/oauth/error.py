"""Errors raised by the OAuth 2.0 client plugin."""

from abc import ABC
from typing import final

from spakky.core.common.error import AbstractSpakkyFrameworkError

from spakky.plugins.oauth.token import OAuthErrorCode, OAuthHttpStatus


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
    """Raised when the token endpoint rejects a request for a non-grant reason.

    Carries only the HTTP status and the RFC 6749 section 5.2 ``error`` code so
    callers can tell configuration errors from transient server failures. The
    response body and request secrets are never kept.
    """

    message = "OAuth token endpoint rejected the request"

    status_code: OAuthHttpStatus
    # None when the response body was not a JSON object with a string error.
    error: OAuthErrorCode | None

    def __init__(
        self,
        status_code: OAuthHttpStatus,
        error: OAuthErrorCode | None = None,
    ) -> None:
        # Passed on so pickle and copy can rebuild the error from its args.
        super().__init__(status_code, error)
        self.status_code = status_code
        self.error = error


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
    """Raised when the revocation endpoint did not confirm a revocation.

    ``status_code`` is None when the server could not be reached; ``error`` is
    None when the response carried no RFC 6749 section 5.2 ``error`` code.
    """

    message = "OAuth token revocation was not confirmed by the server"

    status_code: OAuthHttpStatus | None
    error: OAuthErrorCode | None

    def __init__(
        self,
        status_code: OAuthHttpStatus | None = None,
        error: OAuthErrorCode | None = None,
    ) -> None:
        # Passed on so pickle and copy can rebuild the error from its args.
        super().__init__(status_code, error)
        self.status_code = status_code
        self.error = error


@final
class OAuthRevocationNotSupportedError(AbstractSpakkyOAuthError):
    """Raised when a token is revoked through a registration without an endpoint."""

    message = "OAuth client registration has no revocation endpoint"
