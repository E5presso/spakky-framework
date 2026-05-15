"""Provider-neutral authentication and authorization package root."""

from spakky.auth.constants import (
    AUTH_CONTEXT_CONTEXT_KEY,
    AUTH_CONTEXT_SNAPSHOT_HEADER_KEY,
    AUTH_CONTEXT_SNAPSHOT_METADATA_KEY,
    AUTH_CONTEXT_SNAPSHOT_SCHEMA_VERSION,
    DEFAULT_AUTH_CLOCK_SKEW_SECONDS,
)
from spakky.auth.context import (
    AuthClaim,
    AuthClaimValue,
    AuthContext,
    AuthSubject,
    require_auth_context,
    store_auth_context,
)
from spakky.auth.credential import (
    CredentialCarrier,
    CredentialCarrierKind,
    CredentialCarrierLocation,
)
from spakky.auth.decision import (
    EXPIRED_SNAPSHOT_DECISION,
    INVALID_SNAPSHOT_DECISION,
    MISSING_SNAPSHOT_DECISION,
    VERIFICATION_PROVIDER_UNAVAILABLE_DECISION,
    AuthorizationDecision,
    AuthorizationDecisionState,
    AuthorizationReasonCode,
)
from spakky.auth.error import (
    AbstractSpakkyAuthError,
    AuthContextError,
    AuthContextNotFoundError,
    AuthContextSnapshotError,
    AuthVerificationProviderUnavailableError,
    AuthenticationError,
    AuthorizationError,
    CredentialCarrierError,
    ExpiredAuthContextSnapshotError,
    InvalidAuthContextSnapshotError,
    InvalidAuthContextValueError,
    MissingAuthContextSnapshotError,
)
from spakky.auth.snapshot import AuthContextSnapshot, AuthContextSnapshotSignature
from spakky.core.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-auth")
"""Plugin identifier for the Spakky Auth package."""

__all__ = [
    "AUTH_CONTEXT_CONTEXT_KEY",
    "AUTH_CONTEXT_SNAPSHOT_HEADER_KEY",
    "AUTH_CONTEXT_SNAPSHOT_METADATA_KEY",
    "AUTH_CONTEXT_SNAPSHOT_SCHEMA_VERSION",
    "DEFAULT_AUTH_CLOCK_SKEW_SECONDS",
    "EXPIRED_SNAPSHOT_DECISION",
    "INVALID_SNAPSHOT_DECISION",
    "MISSING_SNAPSHOT_DECISION",
    "PLUGIN_NAME",
    "VERIFICATION_PROVIDER_UNAVAILABLE_DECISION",
    "AbstractSpakkyAuthError",
    "AuthClaim",
    "AuthClaimValue",
    "AuthContext",
    "AuthContextError",
    "AuthContextNotFoundError",
    "AuthContextSnapshot",
    "AuthContextSnapshotError",
    "AuthContextSnapshotSignature",
    "AuthSubject",
    "AuthVerificationProviderUnavailableError",
    "AuthenticationError",
    "AuthorizationDecision",
    "AuthorizationDecisionState",
    "AuthorizationError",
    "AuthorizationReasonCode",
    "CredentialCarrier",
    "CredentialCarrierError",
    "CredentialCarrierKind",
    "CredentialCarrierLocation",
    "ExpiredAuthContextSnapshotError",
    "InvalidAuthContextSnapshotError",
    "InvalidAuthContextValueError",
    "MissingAuthContextSnapshotError",
    "require_auth_context",
    "store_auth_context",
]
