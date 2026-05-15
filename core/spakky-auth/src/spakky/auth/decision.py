"""Authorization decision state and reason model."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Self


class AuthorizationDecisionState(StrEnum):
    """Canonical auth enforcement outcomes."""

    ALLOW = "ALLOW"
    CHALLENGE = "CHALLENGE"
    DENY = "DENY"
    ERROR = "ERROR"


class AuthorizationReasonCode(StrEnum):
    """Machine-readable reason codes attached to authorization decisions."""

    AUTHORIZED = "AUTHORIZED"
    MISSING_CREDENTIAL = "MISSING_CREDENTIAL"
    INVALID_CREDENTIAL = "INVALID_CREDENTIAL"
    EXPIRED_CREDENTIAL = "EXPIRED_CREDENTIAL"
    INSUFFICIENT_ROLE = "INSUFFICIENT_ROLE"
    INSUFFICIENT_SCOPE = "INSUFFICIENT_SCOPE"
    POLICY_DENIED = "POLICY_DENIED"
    SNAPSHOT_MISSING = "SNAPSHOT_MISSING"
    SNAPSHOT_INVALID = "SNAPSHOT_INVALID"
    SNAPSHOT_EXPIRED = "SNAPSHOT_EXPIRED"
    VERIFICATION_PROVIDER_UNAVAILABLE = "VERIFICATION_PROVIDER_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorizationDecision:
    """Provider-neutral result of an auth enforcement decision."""

    state: AuthorizationDecisionState
    """ALLOW, CHALLENGE, DENY, or ERROR."""
    reason_code: AuthorizationReasonCode
    """Machine-readable reason for the decision."""
    reason: str | None = None
    """Optional operator-facing reason text."""

    @classmethod
    def allow(
        cls,
        reason_code: AuthorizationReasonCode = AuthorizationReasonCode.AUTHORIZED,
        reason: str | None = None,
    ) -> Self:
        """Create an ALLOW decision."""
        return cls(
            state=AuthorizationDecisionState.ALLOW,
            reason_code=reason_code,
            reason=reason,
        )

    @classmethod
    def challenge(
        cls,
        reason_code: AuthorizationReasonCode,
        reason: str | None = None,
    ) -> Self:
        """Create a CHALLENGE decision."""
        return cls(
            state=AuthorizationDecisionState.CHALLENGE,
            reason_code=reason_code,
            reason=reason,
        )

    @classmethod
    def deny(
        cls,
        reason_code: AuthorizationReasonCode,
        reason: str | None = None,
    ) -> Self:
        """Create a DENY decision."""
        return cls(
            state=AuthorizationDecisionState.DENY,
            reason_code=reason_code,
            reason=reason,
        )

    @classmethod
    def error(
        cls,
        reason_code: AuthorizationReasonCode,
        reason: str | None = None,
    ) -> Self:
        """Create an ERROR decision."""
        return cls(
            state=AuthorizationDecisionState.ERROR,
            reason_code=reason_code,
            reason=reason,
        )


MISSING_SNAPSHOT_DECISION = AuthorizationDecision.challenge(
    AuthorizationReasonCode.SNAPSHOT_MISSING
)
"""Default decision for missing AuthContextSnapshot propagation metadata."""

INVALID_SNAPSHOT_DECISION = AuthorizationDecision.challenge(
    AuthorizationReasonCode.SNAPSHOT_INVALID
)
"""Default decision for malformed or unsigned AuthContextSnapshot metadata."""

EXPIRED_SNAPSHOT_DECISION = AuthorizationDecision.challenge(
    AuthorizationReasonCode.SNAPSHOT_EXPIRED
)
"""Default decision for expired AuthContextSnapshot metadata."""

VERIFICATION_PROVIDER_UNAVAILABLE_DECISION = AuthorizationDecision.error(
    AuthorizationReasonCode.VERIFICATION_PROVIDER_UNAVAILABLE
)
"""Default decision when snapshot verification provider is unavailable."""
