from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from importlib.metadata import entry_points
import json

import pytest
import spakky.auth
import spakky.plugins.cryptography
from spakky.auth import (
    AuthCapability,
    AuthClaim,
    AuthContext,
    AuthInvocation,
    AuthProviderContribution,
    AuthSnapshotPropagationConfig,
    AuthSubject,
    AuthorizationDecisionState,
    AuthorizationReasonCode,
    AuthVerificationProviderUnavailableError,
    ExpiredAuthContextSnapshotError,
    IAuthContextSnapshotSigner,
    IAuthContextSnapshotVerifier,
    IPasswordHasher,
    IPasswordVerifier,
    InvalidAuthContextSnapshotError,
    MissingAuthContextSnapshotError,
    SnapshotSignRequest,
)
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.cryptography.auth_provider import (
    CRYPTOGRAPHY_AUTH_PROVIDER_ID,
    CryptographyAuthProvider,
    CryptographyAuthProviderConfig,
    cryptography_auth_provider_contribution,
)
from spakky.plugins.cryptography.encoding import Base64Encoder
from spakky.plugins.cryptography.key import Key
from spakky.plugins.cryptography.password.argon2 import Argon2PasswordEncoder
from spakky.plugins.cryptography.password.pbkdf2 import Pbkdf2PasswordEncoder
from spakky.plugins.cryptography.password.scrypt import ScryptPasswordEncoder


def _fixed_clock() -> datetime:
    return datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)


def _later_clock() -> datetime:
    return datetime(2026, 5, 15, 1, 8, 4, tzinfo=UTC)


def _naive_clock() -> datetime:
    return datetime(2026, 5, 15, 1, 2, 3)


def _provider(
    clock: Callable[[], datetime] = _fixed_clock,
) -> CryptographyAuthProvider:
    config = _config(
        snapshot_key=Key(binary=b"0" * 32),
        snapshot_key_id="key:test",
        snapshot_ttl=timedelta(minutes=5),
        clock=clock,
    )
    return CryptographyAuthProvider(config=config)


def _config(**overrides: object) -> CryptographyAuthProviderConfig:
    return CryptographyAuthProviderConfig().model_copy(update=overrides)


def _auth_context() -> AuthContext:
    return AuthContext(
        subject=AuthSubject(id="subject-1", display_name="Subject One"),
        issuer="issuer:test",
        tenant="tenant-1",
        roles=("role:admin",),
        scopes=("documents:read",),
        claims=(AuthClaim(name="email", value="subject@example.com"),),
    )


def _minimal_auth_context() -> AuthContext:
    return AuthContext(
        subject=AuthSubject(id="subject-2"),
        issuer="issuer:test",
        claims=(AuthClaim(name="nullable", value=None),),
    )


def _invocation() -> AuthInvocation:
    return AuthInvocation(boundary="task", operation="documents.process")


def _payload_envelope(payload: dict[str, object]) -> str:
    return Base64Encoder.encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        url_safe=True,
    )


def _signed_payload(provider: CryptographyAuthProvider) -> dict[str, object]:
    snapshot = provider.sign_snapshot(SnapshotSignRequest(auth_context=_auth_context()))
    return provider._decode_envelope(snapshot.base64url_canonical_json())


def test_cryptography_auth_contribution_entry_point_is_declared() -> None:
    contribution_entry_points = entry_points(group="spakky.contributions.spakky.auth")

    assert any(
        entry_point.name == "spakky-cryptography"
        and entry_point.value
        == "spakky.plugins.cryptography.contributions.auth:initialize"
        for entry_point in contribution_entry_points
    )


def test_cryptography_auth_provider_contribution_declares_capabilities() -> None:
    contribution = cryptography_auth_provider_contribution()

    assert contribution.provider_id == CRYPTOGRAPHY_AUTH_PROVIDER_ID
    assert contribution.capabilities == frozenset(
        {
            AuthCapability.SNAPSHOT_SIGN,
            AuthCapability.SNAPSHOT_VERIFY,
            AuthCapability.PASSWORD_HASH,
            AuthCapability.PASSWORD_VERIFY,
        }
    )


def test_load_plugins_with_auth_and_cryptography_registers_provider_contribution() -> (
    None
):
    app = SpakkyApplication(ApplicationContext()).load_plugins(
        include={
            spakky.auth.PLUGIN_NAME,
            spakky.plugins.cryptography.PLUGIN_NAME,
        }
    )
    contributions = app.container.find(
        lambda pod: pod.type_ is AuthProviderContribution
    )

    assert any(
        isinstance(contribution, AuthProviderContribution)
        and contribution.provider_id == CRYPTOGRAPHY_AUTH_PROVIDER_ID
        for contribution in contributions
    )


def test_enabled_snapshot_propagation_starts_with_cryptography_provider() -> None:
    app = SpakkyApplication(ApplicationContext()).load_plugins(
        include={
            spakky.auth.PLUGIN_NAME,
            spakky.plugins.cryptography.PLUGIN_NAME,
        }
    )
    app.add(_enabled_snapshot_propagation_config)

    app.start()
    app.stop()


def test_load_plugins_with_cryptography_expect_auth_ports_bound() -> None:
    """load_plugins()가 cryptography provider를 auth port들에 binding하는지 검증한다."""
    app = SpakkyApplication(ApplicationContext()).load_plugins(
        include={spakky.plugins.cryptography.PLUGIN_NAME}
    )

    app.start()

    assert isinstance(
        app.container.get(IAuthContextSnapshotSigner), CryptographyAuthProvider
    )
    assert isinstance(
        app.container.get(IAuthContextSnapshotVerifier),
        CryptographyAuthProvider,
    )
    assert isinstance(app.container.get(IPasswordHasher), CryptographyAuthProvider)
    assert isinstance(app.container.get(IPasswordVerifier), CryptographyAuthProvider)


def test_snapshot_sign_verify_round_trips_auth_context() -> None:
    provider = _provider()
    snapshot = provider.sign_snapshot(SnapshotSignRequest(auth_context=_auth_context()))

    verified = provider.verify_snapshot(
        snapshot.base64url_canonical_json(), _invocation()
    )

    assert verified == _auth_context()


def test_snapshot_result_returns_allow_with_auth_context() -> None:
    provider = _provider()
    snapshot = provider.sign_snapshot(SnapshotSignRequest(auth_context=_auth_context()))

    result = provider.verify_snapshot_result(
        snapshot.base64url_canonical_json(),
        _invocation(),
    )

    assert result.decision.state == AuthorizationDecisionState.ALLOW
    assert result.auth_context == _auth_context()


def test_snapshot_sign_verify_supports_optional_fields_and_naive_clock() -> None:
    provider = _provider(clock=_naive_clock)
    snapshot = provider.sign_snapshot(
        SnapshotSignRequest(auth_context=_minimal_auth_context())
    )

    verified = provider.verify_snapshot(
        snapshot.base64url_canonical_json(),
        _invocation(),
    )

    assert verified == _minimal_auth_context()


def test_missing_snapshot_verification_raises_and_maps_to_challenge() -> None:
    provider = _provider()

    with pytest.raises(MissingAuthContextSnapshotError):
        provider.verify_snapshot("", _invocation())

    result = provider.verify_snapshot_result("", _invocation())

    assert result.decision.state == AuthorizationDecisionState.CHALLENGE
    assert result.decision.reason_code == AuthorizationReasonCode.SNAPSHOT_MISSING
    assert result.auth_context is None


def test_invalid_snapshot_verification_raises_and_maps_to_challenge() -> None:
    provider = _provider()

    with pytest.raises(InvalidAuthContextSnapshotError):
        provider.verify_snapshot("not-json", _invocation())

    result = provider.verify_snapshot_result("not-json", _invocation())

    assert result.decision.state == AuthorizationDecisionState.CHALLENGE
    assert result.decision.reason_code == AuthorizationReasonCode.SNAPSHOT_INVALID


def test_non_object_snapshot_verification_maps_to_challenge() -> None:
    provider = _provider()
    envelope = Base64Encoder.encode("[]", url_safe=True)

    result = provider.verify_snapshot_result(envelope, _invocation())

    assert result.decision.state == AuthorizationDecisionState.CHALLENGE
    assert result.decision.reason_code == AuthorizationReasonCode.SNAPSHOT_INVALID


def test_snapshot_with_wrong_key_id_maps_to_challenge() -> None:
    provider = _provider()
    payload = _signed_payload(provider)
    signature = provider._dict_value(payload, "signature")
    signature["key_id"] = "key:other"
    payload["signature"] = signature

    result = provider.verify_snapshot_result(_payload_envelope(payload), _invocation())

    assert result.decision.reason_code == AuthorizationReasonCode.SNAPSHOT_INVALID


def test_snapshot_with_wrong_algorithm_maps_to_challenge() -> None:
    provider = _provider()
    payload = _signed_payload(provider)
    signature = provider._dict_value(payload, "signature")
    signature["algorithm"] = "HS512"
    payload["signature"] = signature

    result = provider.verify_snapshot_result(_payload_envelope(payload), _invocation())

    assert result.decision.reason_code == AuthorizationReasonCode.SNAPSHOT_INVALID


def test_snapshot_missing_nested_payload_maps_to_challenge() -> None:
    provider = _provider()
    payload = _signed_payload(provider)
    del payload["signature"]

    result = provider.verify_snapshot_result(_payload_envelope(payload), _invocation())

    assert result.decision.reason_code == AuthorizationReasonCode.SNAPSHOT_INVALID


def test_snapshot_missing_required_string_maps_to_challenge() -> None:
    provider = _provider()
    payload = _signed_payload(provider)
    del payload["issuer"]

    result = provider.verify_snapshot_result(_payload_envelope(payload), _invocation())

    assert result.decision.reason_code == AuthorizationReasonCode.SNAPSHOT_INVALID


def test_snapshot_wrong_optional_string_type_maps_to_challenge() -> None:
    provider = _provider()
    payload = _signed_payload(provider)
    payload["tenant"] = 123

    result = provider.verify_snapshot_result(_payload_envelope(payload), _invocation())

    assert result.decision.reason_code == AuthorizationReasonCode.SNAPSHOT_INVALID


def test_snapshot_invalid_datetime_maps_to_challenge() -> None:
    provider = _provider()
    payload = _signed_payload(provider)
    payload["expires_at"] = "not-a-date"

    result = provider.verify_snapshot_result(_payload_envelope(payload), _invocation())

    assert result.decision.reason_code == AuthorizationReasonCode.SNAPSHOT_INVALID


def test_snapshot_invalid_claim_value_maps_to_challenge() -> None:
    provider = _provider()
    payload = _signed_payload(provider)
    payload["selected_claims"] = {"complex": ["unsupported"]}

    result = provider.verify_snapshot_result(_payload_envelope(payload), _invocation())

    assert result.decision.reason_code == AuthorizationReasonCode.SNAPSHOT_INVALID


def test_non_string_payload_key_raises_invalid_snapshot() -> None:
    provider = _provider()

    with pytest.raises(InvalidAuthContextSnapshotError):
        provider._string_keyed_dict({1: "value"})


def test_default_provider_clock_returns_aware_datetime() -> None:
    now = CryptographyAuthProviderConfig().clock()

    assert now.tzinfo is not None


def test_config_reads_snapshot_key_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPAKKY_CRYPTOGRAPHY_SNAPSHOT_KEY가 Key 설정으로 파싱되는지 검증한다."""
    key = Key(binary=b"2" * 32)
    monkeypatch.setenv("SPAKKY_CRYPTOGRAPHY_SNAPSHOT_KEY", key.b64_urlsafe)

    config = CryptographyAuthProviderConfig()

    assert config.snapshot_key.binary == key.binary


def test_invalid_datetime_value_raises_invalid_snapshot() -> None:
    provider = _provider()

    with pytest.raises(InvalidAuthContextSnapshotError):
        provider._datetime_value({"expires_at": "not-a-date"}, "expires_at")


def test_missing_string_value_raises_invalid_snapshot() -> None:
    provider = _provider()

    with pytest.raises(InvalidAuthContextSnapshotError):
        provider._string_value({}, "issuer")


def test_invalid_optional_string_value_raises_invalid_snapshot() -> None:
    provider = _provider()

    with pytest.raises(InvalidAuthContextSnapshotError):
        provider._optional_string_value({"tenant": 123}, "tenant")


def test_invalid_claim_value_raises_invalid_snapshot() -> None:
    provider = _provider()

    with pytest.raises(InvalidAuthContextSnapshotError):
        provider._claim_value(["unsupported"])


def test_tampered_snapshot_verification_maps_to_challenge() -> None:
    provider = _provider()
    other_provider = CryptographyAuthProvider(
        config=_config(
            snapshot_key=Key(binary=b"1" * 32),
            snapshot_key_id="key:test",
            clock=_fixed_clock,
        )
    )
    snapshot = other_provider.sign_snapshot(
        SnapshotSignRequest(auth_context=_auth_context())
    )

    result = provider.verify_snapshot_result(
        snapshot.base64url_canonical_json(),
        _invocation(),
    )

    assert result.decision.state == AuthorizationDecisionState.CHALLENGE
    assert result.decision.reason_code == AuthorizationReasonCode.SNAPSHOT_INVALID


def test_expired_snapshot_verification_raises_and_maps_to_challenge() -> None:
    signing_provider = _provider()
    verifying_provider = _provider(clock=_later_clock)
    snapshot = signing_provider.sign_snapshot(
        SnapshotSignRequest(auth_context=_auth_context())
    )

    with pytest.raises(ExpiredAuthContextSnapshotError):
        verifying_provider.verify_snapshot(
            snapshot.base64url_canonical_json(), _invocation()
        )

    result = verifying_provider.verify_snapshot_result(
        snapshot.base64url_canonical_json(),
        _invocation(),
    )

    assert result.decision.state == AuthorizationDecisionState.CHALLENGE
    assert result.decision.reason_code == AuthorizationReasonCode.SNAPSHOT_EXPIRED


def test_snapshot_provider_unavailable_maps_to_error() -> None:
    provider = CryptographyAuthProvider(
        config=_config(
            snapshot_key=Key(binary=b"0" * 32),
            verification_available=False,
            clock=_fixed_clock,
        )
    )

    with pytest.raises(AuthVerificationProviderUnavailableError):
        provider.verify_snapshot("snapshot", _invocation())

    result = provider.verify_snapshot_result("snapshot", _invocation())

    assert result.decision.state == AuthorizationDecisionState.ERROR
    assert result.decision.reason_code == (
        AuthorizationReasonCode.VERIFICATION_PROVIDER_UNAVAILABLE
    )


def test_password_hash_verify_returns_allow_for_valid_password() -> None:
    provider = _provider()
    password_hash = provider.hash_password("secret")

    decision = provider.verify_password("secret", password_hash)

    assert decision.state == AuthorizationDecisionState.ALLOW


def test_password_hash_provider_unavailable_raises_auth_error() -> None:
    provider = CryptographyAuthProvider(config=_config(password_available=False))

    with pytest.raises(AuthVerificationProviderUnavailableError):
        provider.hash_password("secret")


def test_password_verify_provider_unavailable_returns_error() -> None:
    provider = CryptographyAuthProvider(config=_config(password_available=False))

    decision = provider.verify_password("secret", "hash")

    assert decision.state == AuthorizationDecisionState.ERROR
    assert decision.reason_code == (
        AuthorizationReasonCode.VERIFICATION_PROVIDER_UNAVAILABLE
    )


@pytest.mark.parametrize(
    "algorithm",
    ["argon2", "pbkdf2", "scrypt"],
)
def test_password_verify_accepts_retained_encoder_hashes(algorithm: str) -> None:
    provider = _provider()
    salt = Key(binary=b"2" * 32)
    if algorithm == "argon2":
        password_hash = Argon2PasswordEncoder(
            password="secret",
            salt=salt,
            time_cost=1,
            memory_cost=8,
            parallelism=1,
        ).encode()
    elif algorithm == "pbkdf2":
        password_hash = Pbkdf2PasswordEncoder(
            password="secret",
            salt=salt,
        ).encode()
    else:
        password_hash = ScryptPasswordEncoder(
            password="secret",
            salt=salt,
        ).encode()

    decision = provider.verify_password("secret", password_hash)

    assert decision.state == AuthorizationDecisionState.ALLOW


def test_password_verify_returns_challenge_for_invalid_password() -> None:
    provider = _provider()
    password_hash = provider.hash_password("secret")

    decision = provider.verify_password("wrong", password_hash)

    assert decision.state == AuthorizationDecisionState.CHALLENGE
    assert decision.reason_code == AuthorizationReasonCode.INVALID_CREDENTIAL


def test_password_verify_returns_challenge_for_unknown_hash_format() -> None:
    provider = _provider()

    decision = provider.verify_password("secret", "unknown:hash")

    assert decision.state == AuthorizationDecisionState.CHALLENGE
    assert decision.reason_code == AuthorizationReasonCode.INVALID_CREDENTIAL


@Pod(name="enabled_snapshot_propagation_config")
def _enabled_snapshot_propagation_config() -> AuthSnapshotPropagationConfig:
    return AuthSnapshotPropagationConfig(enabled=True)
