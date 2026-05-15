"""AuthContext model and ApplicationContext storage helpers."""

from dataclasses import dataclass, field

from spakky.auth.constants import AUTH_CONTEXT_CONTEXT_KEY
from spakky.auth.credential import CredentialCarrier
from spakky.auth.error import AuthContextNotFoundError, InvalidAuthContextValueError
from spakky.core.pod.interfaces.application_context import IApplicationContext

AuthClaimValue = str | int | float | bool | None


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthClaim:
    """Selected provider claim safe for framework-level auth decisions."""

    name: str
    """Canonical claim name."""

    value: AuthClaimValue
    """JSON-scalar claim value."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthSubject:
    """Authenticated subject identity."""

    id: str
    """Stable provider-neutral subject identifier."""

    display_name: str | None = None
    """Optional human-readable subject label."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthContext:
    """Request/context-scoped authentication state seeded by inbound adapters."""

    subject: AuthSubject
    """Authenticated subject."""

    issuer: str
    """Authority that authenticated the subject."""

    tenant: str | None = None
    """Optional tenant canonical reference."""

    roles: tuple[str, ...] = ()
    """Role canonical references granted to the subject."""

    scopes: tuple[str, ...] = ()
    """Scope canonical references granted to the subject."""

    claims: tuple[AuthClaim, ...] = ()
    """Selected provider claims retained for downstream decisions."""

    credential_carrier: CredentialCarrier | None = None
    """Boundary-local credential carrier that produced this context."""
    metadata: tuple[AuthClaim, ...] = field(default_factory=tuple)
    """Framework-safe metadata associated with this auth context."""


def store_auth_context(
    application_context: IApplicationContext,
    auth_context: AuthContext,
) -> None:
    """Store AuthContext in ApplicationContext context values."""
    application_context.set_context_value(AUTH_CONTEXT_CONTEXT_KEY, auth_context)


def require_auth_context(application_context: IApplicationContext) -> AuthContext:
    """Load AuthContext from ApplicationContext or raise an auth error."""
    value = application_context.get_context_value(AUTH_CONTEXT_CONTEXT_KEY)
    if isinstance(value, AuthContext):
        return value
    if value is None:
        raise AuthContextNotFoundError()
    raise InvalidAuthContextValueError()
