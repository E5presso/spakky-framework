"""Auth snapshot and password capabilities backed by cryptographic utilities."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import override
import json

from spakky.auth import (
    AuthCapability,
    AuthClaim,
    AuthClaimValue,
    AuthContext,
    AuthContextSnapshot,
    AuthContextSnapshotSignature,
    AuthInvocation,
    AuthProviderContribution,
    AuthSubject,
    AuthorizationDecision,
    AuthorizationReasonCode,
    AuthPasswordHash,
    AuthPasswordPlaintext,
    AuthVerificationProviderUnavailableError,
    ExpiredAuthContextSnapshotError,
    IAuthContextSnapshotSigner,
    IAuthContextSnapshotVerifier,
    InvalidAuthContextSnapshotError,
    IPasswordHasher,
    IPasswordVerifier,
    MissingAuthContextSnapshotError,
    SnapshotSignRequest,
)
from spakky.auth.constants import AUTH_CONTEXT_SNAPSHOT_SCHEMA_VERSION
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.cryptography.encoding import Base64Encoder
from spakky.plugins.cryptography.hmac_signer import HMAC, HMACType
from spakky.plugins.cryptography.key import Key
from spakky.plugins.cryptography.password.argon2 import Argon2PasswordEncoder
from spakky.plugins.cryptography.password.bcrypt import BcryptPasswordEncoder
from spakky.plugins.cryptography.password.pbkdf2 import Pbkdf2PasswordEncoder
from spakky.plugins.cryptography.password.scrypt import ScryptPasswordEncoder

CRYPTOGRAPHY_AUTH_PROVIDER_ID = "provider:spakky-cryptography"
"""Stable auth provider id advertised by spakky-cryptography."""

SNAPSHOT_SIGNATURE_ALGORITHM = "HS256"
"""Snapshot envelope signature algorithm used by this provider."""

JsonObject = dict[str, object]


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class CryptographyAuthProviderConfig:
    """Runtime config for cryptography auth provider capabilities."""

    snapshot_key: Key = field(default_factory=lambda: Key(size=32))
    """HMAC key used to sign and verify AuthContextSnapshot envelopes."""

    snapshot_key_id: str = "spakky-cryptography:default"
    """Identifier carried in signed snapshot envelopes."""

    snapshot_ttl: timedelta = timedelta(minutes=5)
    """Validity window for newly signed snapshots."""

    clock: Callable[[], datetime] = _utc_now
    """Clock used for signing and expiration validation."""

    verification_available: bool = True
    """Whether snapshot verification provider dependencies are available."""

    password_available: bool = True
    """Whether password hashing provider dependencies are available."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthContextSnapshotVerificationResult:
    """Decision plus optional AuthContext produced by snapshot verification."""

    decision: AuthorizationDecision
    """ALLOW, CHALLENGE, or ERROR decision for the verification attempt."""

    auth_context: AuthContext | None = None
    """Verified auth context when decision is ALLOW."""


@Pod()
class CryptographyAuthProvider(
    IAuthContextSnapshotSigner,
    IAuthContextSnapshotVerifier,
    IPasswordHasher,
    IPasswordVerifier,
):
    """Cryptography-backed provider for snapshot and password auth capabilities."""

    _config: CryptographyAuthProviderConfig

    def __init__(
        self,
        config: CryptographyAuthProviderConfig = CryptographyAuthProviderConfig(),
    ) -> None:
        self._config = config

    @override
    def sign_snapshot(self, request: SnapshotSignRequest) -> AuthContextSnapshot:
        """Create a signed AuthContextSnapshot envelope."""
        issued_at = self._aware_datetime(self._config.clock())
        tenant = (
            request.tenant
            if request.tenant is not None
            else request.auth_context.tenant
        )
        unsigned_payload = self._unsigned_payload(
            auth_context=request.auth_context,
            tenant=tenant,
            issued_at=issued_at,
            expires_at=issued_at + self._config.snapshot_ttl,
        )
        signature = HMAC.sign_text(
            self._config.snapshot_key,
            HMACType.HS256,
            self._canonical_json(unsigned_payload),
            url_safe=True,
        )
        return AuthContextSnapshot(
            subject=request.auth_context.subject,
            issuer=request.auth_context.issuer,
            issued_at=issued_at,
            expires_at=issued_at + self._config.snapshot_ttl,
            signature=AuthContextSnapshotSignature(
                key_id=self._config.snapshot_key_id,
                algorithm=SNAPSHOT_SIGNATURE_ALGORITHM,
                signature=signature,
            ),
            tenant=tenant,
            roles=request.auth_context.roles,
            scopes=request.auth_context.scopes,
            selected_claims=request.auth_context.claims,
        )

    @override
    def verify_snapshot(
        self,
        snapshot_envelope: str,
        invocation: AuthInvocation,
    ) -> AuthContext:
        """Verify a signed snapshot envelope and return its AuthContext."""
        if not self._config.verification_available:
            raise AuthVerificationProviderUnavailableError()
        if snapshot_envelope == "":
            raise MissingAuthContextSnapshotError()
        payload = self._decode_envelope(snapshot_envelope)
        self._verify_payload_signature(payload)
        expires_at = self._datetime_value(payload, "expires_at")
        if expires_at < self._aware_datetime(self._config.clock()):
            raise ExpiredAuthContextSnapshotError()
        return self._auth_context_from_payload(payload)

    def verify_snapshot_result(
        self,
        snapshot_envelope: str,
        invocation: AuthInvocation,
    ) -> AuthContextSnapshotVerificationResult:
        """Verify a snapshot envelope and map auth errors to decisions."""
        try:
            auth_context = self.verify_snapshot(snapshot_envelope, invocation)
        except MissingAuthContextSnapshotError:
            return AuthContextSnapshotVerificationResult(
                decision=AuthorizationDecision.challenge(
                    AuthorizationReasonCode.SNAPSHOT_MISSING
                )
            )
        except InvalidAuthContextSnapshotError:
            return AuthContextSnapshotVerificationResult(
                decision=AuthorizationDecision.challenge(
                    AuthorizationReasonCode.SNAPSHOT_INVALID
                )
            )
        except ExpiredAuthContextSnapshotError:
            return AuthContextSnapshotVerificationResult(
                decision=AuthorizationDecision.challenge(
                    AuthorizationReasonCode.SNAPSHOT_EXPIRED
                )
            )
        except AuthVerificationProviderUnavailableError:
            return AuthContextSnapshotVerificationResult(
                decision=AuthorizationDecision.error(
                    AuthorizationReasonCode.VERIFICATION_PROVIDER_UNAVAILABLE
                )
            )
        return AuthContextSnapshotVerificationResult(
            decision=AuthorizationDecision.allow(),
            auth_context=auth_context,
        )

    @override
    def hash_password(self, password: AuthPasswordPlaintext) -> AuthPasswordHash:
        """Hash plaintext password material for storage."""
        if not self._config.password_available:
            raise AuthVerificationProviderUnavailableError()
        return BcryptPasswordEncoder(password=password).encode()

    @override
    def verify_password(
        self,
        password: AuthPasswordPlaintext,
        password_hash: AuthPasswordHash,
    ) -> AuthorizationDecision:
        """Verify plaintext password material against a retained password hash."""
        if not self._config.password_available:
            return AuthorizationDecision.error(
                AuthorizationReasonCode.VERIFICATION_PROVIDER_UNAVAILABLE
            )
        try:
            if self._password_encoder(password_hash).challenge(password):
                return AuthorizationDecision.allow()
        except Exception:
            return AuthorizationDecision.challenge(
                AuthorizationReasonCode.INVALID_CREDENTIAL
            )
        return AuthorizationDecision.challenge(
            AuthorizationReasonCode.INVALID_CREDENTIAL
        )

    def _unsigned_payload(
        self,
        auth_context: AuthContext,
        tenant: str | None,
        issued_at: datetime,
        expires_at: datetime,
    ) -> JsonObject:
        selected_claims = {
            claim.name: claim.value
            for claim in sorted(auth_context.claims, key=lambda claim: claim.name)
        }
        return {
            "correlation_id": None,
            "delegation_chain": (),
            "expires_at": expires_at.isoformat(),
            "issued_at": issued_at.isoformat(),
            "issuer": auth_context.issuer,
            "roles": auth_context.roles,
            "schema_version": AUTH_CONTEXT_SNAPSHOT_SCHEMA_VERSION,
            "scopes": auth_context.scopes,
            "selected_claims": selected_claims,
            "subject": {
                "display_name": auth_context.subject.display_name,
                "id": auth_context.subject.id,
            },
            "tenant": tenant,
        }

    def _decode_envelope(self, snapshot_envelope: str) -> JsonObject:
        try:
            decoded = Base64Encoder.get_bytes(snapshot_envelope, url_safe=True).decode(
                "UTF-8"
            )
            payload = json.loads(decoded)
            if isinstance(payload, dict):
                return self._string_keyed_dict(payload)
        except Exception as exc:
            raise InvalidAuthContextSnapshotError() from exc
        raise InvalidAuthContextSnapshotError()

    def _verify_payload_signature(self, payload: JsonObject) -> None:
        signature_payload = self._dict_value(payload, "signature")
        key_id = self._string_value(signature_payload, "key_id")
        algorithm = self._string_value(signature_payload, "algorithm")
        signature = self._string_value(signature_payload, "signature")
        if key_id != self._config.snapshot_key_id:
            raise InvalidAuthContextSnapshotError()
        if algorithm != SNAPSHOT_SIGNATURE_ALGORITHM:
            raise InvalidAuthContextSnapshotError()
        unsigned_payload = dict(payload)
        del unsigned_payload["signature"]
        valid = HMAC.verify(
            self._config.snapshot_key,
            HMACType.HS256,
            self._canonical_json(unsigned_payload),
            signature,
            url_safe=True,
        )
        if not valid:
            raise InvalidAuthContextSnapshotError()

    def _auth_context_from_payload(self, payload: JsonObject) -> AuthContext:
        subject_payload = self._dict_value(payload, "subject")
        return AuthContext(
            subject=AuthSubject(
                id=self._string_value(subject_payload, "id"),
                display_name=self._optional_string_value(
                    subject_payload,
                    "display_name",
                ),
            ),
            issuer=self._string_value(payload, "issuer"),
            tenant=self._optional_string_value(payload, "tenant"),
            roles=self._string_tuple_value(payload, "roles"),
            scopes=self._string_tuple_value(payload, "scopes"),
            claims=self._claims_value(payload, "selected_claims"),
        )

    def _password_encoder(
        self,
        password_hash: AuthPasswordHash,
    ) -> (
        Argon2PasswordEncoder
        | BcryptPasswordEncoder
        | Pbkdf2PasswordEncoder
        | ScryptPasswordEncoder
    ):
        if password_hash.startswith(f"{Argon2PasswordEncoder.ALGORITHM_TYPE}:"):
            return Argon2PasswordEncoder(password_hash=password_hash)
        if password_hash.startswith(f"{BcryptPasswordEncoder.ALGORITHM_TYPE}:"):
            return BcryptPasswordEncoder(password_hash=password_hash)
        if password_hash.startswith(f"{Pbkdf2PasswordEncoder.ALGORITHM_TYPE}:"):
            return Pbkdf2PasswordEncoder(password_hash=password_hash)
        if password_hash.startswith(f"{ScryptPasswordEncoder.ALGORITHM_TYPE}:"):
            return ScryptPasswordEncoder(password_hash=password_hash)
        raise InvalidAuthContextSnapshotError()

    def _datetime_value(self, payload: JsonObject, key: str) -> datetime:
        try:
            return self._aware_datetime(
                datetime.fromisoformat(self._string_value(payload, key))
            )
        except Exception as exc:
            raise InvalidAuthContextSnapshotError() from exc

    def _aware_datetime(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    def _canonical_json(self, payload: JsonObject) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def _dict_value(self, payload: JsonObject, key: str) -> JsonObject:
        value = payload.get(key)
        if isinstance(value, dict):
            return self._string_keyed_dict(value)
        raise InvalidAuthContextSnapshotError()

    def _string_value(self, payload: JsonObject, key: str) -> str:
        value = payload.get(key)
        if isinstance(value, str):
            return value
        raise InvalidAuthContextSnapshotError()

    def _optional_string_value(self, payload: JsonObject, key: str) -> str | None:
        value = payload.get(key)
        if value is None:
            return None
        if isinstance(value, str):
            return value
        raise InvalidAuthContextSnapshotError()

    def _string_tuple_value(self, payload: JsonObject, key: str) -> tuple[str, ...]:
        value = payload.get(key)
        if isinstance(value, list | tuple):
            items: list[str] = []
            for item in value:
                if not isinstance(item, str):
                    raise InvalidAuthContextSnapshotError()
                items.append(item)
            return tuple(items)
        raise InvalidAuthContextSnapshotError()

    def _claims_value(self, payload: JsonObject, key: str) -> tuple[AuthClaim, ...]:
        claims = self._dict_value(payload, key)
        return tuple(
            AuthClaim(name=name, value=self._claim_value(value))
            for name, value in sorted(claims.items())
        )

    def _claim_value(self, value: object) -> AuthClaimValue:
        if value is None:
            return None
        if isinstance(value, str | int | float | bool):
            return value
        raise InvalidAuthContextSnapshotError()

    def _string_keyed_dict(self, payload: dict[object, object]) -> JsonObject:
        result: JsonObject = {}
        for key, value in payload.items():
            if not isinstance(key, str):
                raise InvalidAuthContextSnapshotError()
            result[key] = value
        return result


@Pod(name="spakky_cryptography_auth_provider_contribution")
def cryptography_auth_provider_contribution() -> AuthProviderContribution:
    """Return the auth capabilities contributed by spakky-cryptography."""
    return AuthProviderContribution(
        provider_id=CRYPTOGRAPHY_AUTH_PROVIDER_ID,
        capabilities=frozenset(
            {
                AuthCapability.SNAPSHOT_SIGN,
                AuthCapability.SNAPSHOT_VERIFY,
                AuthCapability.PASSWORD_HASH,
                AuthCapability.PASSWORD_VERIFY,
            }
        ),
    )
