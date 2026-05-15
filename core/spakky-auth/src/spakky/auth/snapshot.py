"""Signed AuthContextSnapshot envelope contract."""

from dataclasses import dataclass
from datetime import datetime
from base64 import urlsafe_b64encode
import json

from spakky.auth.constants import AUTH_CONTEXT_SNAPSHOT_SCHEMA_VERSION
from spakky.auth.context import AuthClaim, AuthSubject


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthContextSnapshotSignature:
    """Signature material carried with a signed AuthContextSnapshot envelope."""

    key_id: str
    """Provider key identifier used to verify the envelope."""
    algorithm: str
    """Signature algorithm name."""
    signature: str
    """Base64url signature bytes produced by the signer provider."""

    def canonical_payload(self) -> dict[str, str]:
        """Return canonical JSON-ready signature material."""
        return {
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "signature": self.signature,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthContextSnapshot:
    """Canonical JSON signed envelope propagated instead of raw credentials."""

    subject: AuthSubject
    """Subject represented by this snapshot."""
    issuer: str
    """Issuer that created the snapshot."""
    issued_at: datetime
    """Snapshot issue timestamp."""
    expires_at: datetime
    """Snapshot expiration timestamp."""
    signature: AuthContextSnapshotSignature
    """Signature material required by verification providers."""
    schema_version: int = AUTH_CONTEXT_SNAPSHOT_SCHEMA_VERSION
    """Canonical snapshot schema version."""
    tenant: str | None = None
    """Optional tenant canonical reference."""
    roles: tuple[str, ...] = ()
    """Role canonical references included in the snapshot."""
    scopes: tuple[str, ...] = ()
    """Scope canonical references included in the snapshot."""
    selected_claims: tuple[AuthClaim, ...] = ()
    """Selected claims included in the signed snapshot."""
    correlation_id: str | None = None
    """Optional trace/correlation reference for the propagated context."""
    delegation_chain: tuple[str, ...] = ()
    """Ordered subject/service delegation references."""

    def canonical_payload(self) -> dict[str, object]:
        """Return canonical JSON-ready signed envelope payload."""
        selected_claims = {
            claim.name: claim.value
            for claim in sorted(self.selected_claims, key=lambda claim: claim.name)
        }
        return {
            "correlation_id": self.correlation_id,
            "delegation_chain": self.delegation_chain,
            "expires_at": self.expires_at.isoformat(),
            "issued_at": self.issued_at.isoformat(),
            "issuer": self.issuer,
            "roles": self.roles,
            "schema_version": self.schema_version,
            "scopes": self.scopes,
            "selected_claims": selected_claims,
            "signature": self.signature.canonical_payload(),
            "subject": {
                "display_name": self.subject.display_name,
                "id": self.subject.id,
            },
            "tenant": self.tenant,
        }

    def canonical_json(self) -> str:
        """Return compact, sorted canonical JSON for the signed envelope."""
        return json.dumps(
            self.canonical_payload(),
            sort_keys=True,
            separators=(",", ":"),
        )

    def base64url_canonical_json(self) -> str:
        """Return unpadded base64url canonical JSON envelope text."""
        encoded = urlsafe_b64encode(self.canonical_json().encode())
        return encoded.decode().rstrip("=")
