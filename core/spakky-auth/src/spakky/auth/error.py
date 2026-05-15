"""Error hierarchy for spakky-auth semantic model contracts."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyAuthError(AbstractSpakkyFrameworkError, ABC):
    """Base class for all spakky-auth errors."""

    ...


class AuthContextError(AbstractSpakkyAuthError):
    """Raised when AuthContext storage or lookup fails."""

    message = "Auth context is unavailable or invalid"


class AuthContextNotFoundError(AuthContextError):
    """Raised when ApplicationContext has no AuthContext value."""

    message = "Auth context was not found in ApplicationContext"


class InvalidAuthContextValueError(AuthContextError):
    """Raised when ApplicationContext contains a non-AuthContext value."""

    message = "ApplicationContext auth value is not an AuthContext"


class CredentialCarrierError(AbstractSpakkyAuthError):
    """Raised when a credential carrier cannot be interpreted."""

    message = "Credential carrier is invalid"


class AuthenticationError(AbstractSpakkyAuthError):
    """Raised when authentication fails before authorization policy evaluation."""

    message = "Authentication failed"


class AuthorizationError(AbstractSpakkyAuthError):
    """Raised when authorization policy evaluation denies access."""

    message = "Authorization failed"


class AuthContextSnapshotError(AbstractSpakkyAuthError):
    """Raised when an AuthContextSnapshot cannot be used."""

    message = "Auth context snapshot is invalid"


class MissingAuthContextSnapshotError(AuthContextSnapshotError):
    """Raised when snapshot propagation metadata is absent."""

    message = "Auth context snapshot is missing"


class InvalidAuthContextSnapshotError(AuthContextSnapshotError):
    """Raised when snapshot propagation metadata is malformed or unsigned."""

    message = "Auth context snapshot is invalid"


class ExpiredAuthContextSnapshotError(AuthContextSnapshotError):
    """Raised when snapshot propagation metadata is outside its time window."""

    message = "Auth context snapshot is expired"


class AuthVerificationProviderUnavailableError(AuthContextSnapshotError):
    """Raised when snapshot verification cannot reach its provider."""

    message = "Auth verification provider is unavailable"
