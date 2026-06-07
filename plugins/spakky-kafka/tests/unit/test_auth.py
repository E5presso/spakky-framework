"""Unit tests for Kafka AuthContext snapshot boundary helpers."""

from typing import override
from unittest.mock import Mock

import pytest
from spakky.auth import (
    AUTH_CONTEXT_SNAPSHOT_HEADER_KEY,
    AUTH_CONTEXT_SNAPSHOT_METADATA_KEY,
    AuthContext,
    AuthInvocation,
    AuthSubject,
    AuthVerificationProviderUnavailableError,
    AuthorizationDecisionState,
    ExpiredAuthContextSnapshotError,
    IAuthContextSnapshotVerifier,
    InvalidAuthContextSnapshotError,
    MissingAuthContextSnapshotError,
    require_auth_context,
)
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.interfaces.container import IContainer

from spakky.plugins.kafka.auth import (
    KAFKA_AUTH_BOUNDARY,
    KafkaAuthBoundary,
    KafkaHandlerAuthBinding,
)


class RecordingSnapshotVerifier(IAuthContextSnapshotVerifier):
    """Snapshot verifier fake recording its input and raising configured errors."""

    snapshot: str | None
    invocation: AuthInvocation | None
    error: Exception | None

    def __init__(self, error: Exception | None = None) -> None:
        self.snapshot = None
        self.invocation = None
        self.error = error

    @override
    def verify_snapshot(
        self,
        snapshot_envelope: str,
        invocation: AuthInvocation,
    ) -> AuthContext:
        self.snapshot = snapshot_envelope
        self.invocation = invocation
        if self.error is not None:
            raise self.error
        return AuthContext(
            subject=AuthSubject(id="user:kafka"),
            issuer="test-verifier",
        )


def _container(verifier: IAuthContextSnapshotVerifier | None) -> IContainer:
    container = Mock(spec=IContainer)
    container.get_or_none.side_effect = lambda type_: (
        verifier if type_ is IAuthContextSnapshotVerifier else None
    )
    return container


def _binding(protected: bool = True) -> KafkaHandlerAuthBinding:
    return KafkaHandlerAuthBinding(
        operation="tests.handlers.SampleHandler.handle",
        protected=protected,
    )


def test_seed_auth_context_with_snapshot_header_expect_context_stored() -> None:
    """x-spakky-auth-context-snapshot header is verified and seeded."""
    application_context = ApplicationContext()
    verifier = RecordingSnapshotVerifier()
    boundary = KafkaAuthBoundary(_container(verifier), application_context)

    decision = boundary.seed_auth_context(
        {AUTH_CONTEXT_SNAPSHOT_HEADER_KEY: "snapshot-envelope"},
        _binding(),
    )

    assert decision.state is AuthorizationDecisionState.ALLOW
    assert verifier.snapshot == "snapshot-envelope"
    assert verifier.invocation is not None
    assert verifier.invocation.boundary == KAFKA_AUTH_BOUNDARY
    assert verifier.invocation.operation == "tests.handlers.SampleHandler.handle"
    assert require_auth_context(application_context).subject.id == "user:kafka"


def test_seed_auth_context_reads_metadata_header_fallback() -> None:
    """Outbound event metadata key is accepted as a Kafka snapshot header."""
    verifier = RecordingSnapshotVerifier()
    boundary = KafkaAuthBoundary(_container(verifier), ApplicationContext())

    decision = boundary.seed_auth_context(
        {AUTH_CONTEXT_SNAPSHOT_METADATA_KEY.upper(): "metadata-envelope"},
        _binding(),
    )

    assert decision.state is AuthorizationDecisionState.ALLOW
    assert verifier.snapshot == "metadata-envelope"


def test_protected_handler_missing_snapshot_challenges() -> None:
    """Protected handlers fail closed when no snapshot is present."""
    boundary = KafkaAuthBoundary(_container(None), ApplicationContext())

    decision = boundary.seed_auth_context({}, _binding())

    assert decision.state is AuthorizationDecisionState.CHALLENGE


def test_public_handler_missing_snapshot_allows_without_provider() -> None:
    """Public Kafka handlers preserve existing no-auth message behavior."""
    boundary = KafkaAuthBoundary(_container(None), ApplicationContext())

    decision = boundary.seed_auth_context({}, _binding(protected=False))

    assert decision.state is AuthorizationDecisionState.ALLOW


@pytest.mark.parametrize(
    ("error", "expected_state"),
    [
        (MissingAuthContextSnapshotError(), AuthorizationDecisionState.CHALLENGE),
        (InvalidAuthContextSnapshotError(), AuthorizationDecisionState.CHALLENGE),
        (ExpiredAuthContextSnapshotError(), AuthorizationDecisionState.CHALLENGE),
    ],
)
def test_snapshot_verification_challenge_fail_closed(
    error: Exception,
    expected_state: AuthorizationDecisionState,
) -> None:
    """Missing, invalid, and expired envelopes map to CHALLENGE."""
    verifier = RecordingSnapshotVerifier(error=error)
    boundary = KafkaAuthBoundary(_container(verifier), ApplicationContext())

    decision = boundary.seed_auth_context(
        {AUTH_CONTEXT_SNAPSHOT_HEADER_KEY: "snapshot-envelope"},
        _binding(),
    )

    assert decision.state is expected_state


def test_snapshot_provider_unavailable_is_retryable_error() -> None:
    """Verifier provider unavailability is propagated instead of swallowed."""
    verifier = RecordingSnapshotVerifier(
        error=AuthVerificationProviderUnavailableError()
    )
    boundary = KafkaAuthBoundary(_container(verifier), ApplicationContext())

    with pytest.raises(AuthVerificationProviderUnavailableError):
        boundary.seed_auth_context(
            {AUTH_CONTEXT_SNAPSHOT_HEADER_KEY: "snapshot-envelope"},
            _binding(),
        )


def test_missing_snapshot_provider_is_retryable_error() -> None:
    """Snapshot-bearing messages require a verifier provider."""
    boundary = KafkaAuthBoundary(_container(None), ApplicationContext())

    with pytest.raises(AuthVerificationProviderUnavailableError):
        boundary.seed_auth_context(
            {AUTH_CONTEXT_SNAPSHOT_HEADER_KEY: "snapshot-envelope"},
            _binding(),
        )
