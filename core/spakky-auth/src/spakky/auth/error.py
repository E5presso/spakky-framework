"""Error hierarchy for spakky-auth semantic model contracts."""

from abc import ABC

from spakky.auth.decision import AuthorizationDecision, AuthorizationReasonCode
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


class ConflictingAuthMetadataError(AuthorizationError):
    """Raised when public and protected auth metadata are both effective."""

    message = "Public access and protected auth requirements conflict"


class AuthRequirementDeniedError(AuthorizationError):
    """Raised when an auth requirement decision is not ALLOW."""

    message = "Authorization requirement was not allowed"
    decision: AuthorizationDecision | None

    def __init__(self, decision: AuthorizationDecision | None = None) -> None:
        self.decision = decision
        super().__init__()


class AuthDynamicRefUnresolvedError(AuthRequirementDeniedError):
    """Raised when a late-bound auth reference has no value for this invocation.

    The requirement fails closed: a boundary that stores no AuthInvocation, an
    absent or empty invocation attribute, and a resolver answering with another
    reference kind all deny the call.
    """

    message = "Dynamic auth reference could not be resolved from the invocation"
    expression: str

    def __init__(self, expression: str) -> None:
        self.expression = expression
        super().__init__(
            AuthorizationDecision.deny(
                AuthorizationReasonCode.DYNAMIC_REF_UNRESOLVED,
                reason=self.message,
            )
        )


class InvalidAuthDynamicRefKindError(AuthorizationError):
    """Raised when a dynamic ref of the wrong kind is declared for a field."""

    message = "Dynamic auth reference kind does not match the requirement field"


class AuthRequirementProviderUnavailableError(AuthorizationError):
    """Raised when no provider is available for a protected requirement."""

    message = "Authorization requirement provider is unavailable"


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
