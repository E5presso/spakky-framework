"""Tests for RabbitMQ auth snapshot boundary helpers."""

from collections.abc import Mapping

import pytest
from spakky.auth import (
    AUTH_CONTEXT_SNAPSHOT_HEADER_KEY,
    AUTH_CONTEXT_SNAPSHOT_METADATA_KEY,
    EXPIRED_SNAPSHOT_DECISION,
    INVALID_SNAPSHOT_DECISION,
    MISSING_SNAPSHOT_DECISION,
    VERIFICATION_PROVIDER_UNAVAILABLE_DECISION,
    AuthContext,
    AuthInvocation,
    AuthRequirementDeniedError,
    AuthSubject,
    AuthVerificationProviderUnavailableError,
    ExpiredAuthContextSnapshotError,
    IAuthContextSnapshotVerifier,
    InvalidAuthContextSnapshotError,
    MissingAuthContextSnapshotError,
    require_auth_context,
)
from spakky.core.application.application_context import ApplicationContext
from spakky.domain.models.event import AbstractIntegrationEvent
from typing import override

from spakky.plugins.rabbitmq.auth import (
    RABBITMQ_AUTH_BOUNDARY,
    RabbitMQAuthBoundary,
    current_rabbitmq_message_headers,
    reset_current_rabbitmq_message_headers,
    set_current_rabbitmq_message_headers,
)


class SampleIntegrationEvent(AbstractIntegrationEvent):
    """Sample integration event for auth boundary tests."""

    data: str


class RecordingSnapshotVerifier(IAuthContextSnapshotVerifier):
    """Snapshot verifier stub that records the envelope and invocation."""

    auth_context: AuthContext
    error: Exception | None
    envelope: str | None
    invocation: AuthInvocation | None

    def __init__(self, error: Exception | None = None) -> None:
        self.auth_context = AuthContext(
            subject=AuthSubject(id="subject-1"),
            issuer="issuer-1",
            scopes=("rabbitmq:consume",),
        )
        self.error = error
        self.envelope = None
        self.invocation = None

    @override
    def verify_snapshot(
        self,
        snapshot_envelope: str,
        invocation: AuthInvocation,
    ) -> AuthContext:
        self.envelope = snapshot_envelope
        self.invocation = invocation
        if self.error is not None:
            raise self.error
        return self.auth_context


def test_current_headers_default_empty_expect_empty_mapping() -> None:
    """메시지 헤더 컨텍스트가 없으면 빈 mapping을 반환한다."""
    assert current_rabbitmq_message_headers() == {}


def test_set_and_reset_current_headers_expect_previous_context_restored() -> None:
    """ContextVar token reset으로 이전 RabbitMQ 헤더 컨텍스트가 복원된다."""
    outer = set_current_rabbitmq_message_headers({"outer": "1"})
    inner = set_current_rabbitmq_message_headers({"inner": "2"})
    try:
        assert current_rabbitmq_message_headers() == {"inner": "2"}
        reset_current_rabbitmq_message_headers(inner)
        assert current_rabbitmq_message_headers() == {"outer": "1"}
    finally:
        reset_current_rabbitmq_message_headers(outer)


def test_seed_auth_context_with_metadata_key_expect_context_stored() -> None:
    """metadata key의 signed snapshot을 검증하고 AuthContext를 저장한다."""
    application_context = ApplicationContext()
    verifier = RecordingSnapshotVerifier()
    boundary = RabbitMQAuthBoundary(application_context, verifier)
    token = set_current_rabbitmq_message_headers(
        {AUTH_CONTEXT_SNAPSHOT_METADATA_KEY: "metadata-snapshot"}
    )
    try:
        boundary.seed_auth_context(
            event_type=SampleIntegrationEvent,
            operation="Handler.handle",
            protected=True,
        )
    finally:
        reset_current_rabbitmq_message_headers(token)

    assert require_auth_context(application_context).subject.id == "subject-1"
    assert verifier.envelope == "metadata-snapshot"
    assert verifier.invocation is not None
    assert verifier.invocation.boundary == RABBITMQ_AUTH_BOUNDARY
    assert verifier.invocation.operation == "Handler.handle"


def test_seed_auth_context_with_header_key_expect_context_stored() -> None:
    """x-spakky-auth-context-snapshot header를 검증하고 AuthContext를 저장한다."""
    application_context = ApplicationContext()
    verifier = RecordingSnapshotVerifier()
    boundary = RabbitMQAuthBoundary(application_context, verifier)
    token = set_current_rabbitmq_message_headers(
        {AUTH_CONTEXT_SNAPSHOT_HEADER_KEY: "header-snapshot"}
    )
    try:
        boundary.seed_auth_context(
            event_type=SampleIntegrationEvent,
            operation="Handler.handle",
            protected=True,
        )
    finally:
        reset_current_rabbitmq_message_headers(token)

    assert require_auth_context(application_context).subject.id == "subject-1"
    assert verifier.envelope == "header-snapshot"


def test_seed_auth_context_unprotected_missing_snapshot_expect_noop() -> None:
    """보호되지 않은 handler는 snapshot이 없어도 allow-all로 진행한다."""
    application_context = ApplicationContext()
    boundary = RabbitMQAuthBoundary(application_context, RecordingSnapshotVerifier())

    boundary.seed_auth_context(
        event_type=SampleIntegrationEvent,
        operation="Handler.handle",
        protected=False,
    )

    assert application_context.get_context_value("spakky.auth.context") is None


def test_seed_auth_context_protected_missing_snapshot_expect_challenge() -> None:
    """보호된 handler에서 snapshot이 없으면 CHALLENGE로 fail-closed 처리한다."""
    application_context = ApplicationContext()
    boundary = RabbitMQAuthBoundary(application_context, RecordingSnapshotVerifier())

    with pytest.raises(AuthRequirementDeniedError) as excinfo:
        boundary.seed_auth_context(
            event_type=SampleIntegrationEvent,
            operation="Handler.handle",
            protected=True,
        )

    assert excinfo.value.decision == MISSING_SNAPSHOT_DECISION


def test_seed_auth_context_verifier_unavailable_expect_error() -> None:
    """검증 provider가 없으면 ERROR decision으로 fail-closed 처리한다."""
    application_context = ApplicationContext()
    boundary = RabbitMQAuthBoundary(application_context, None)
    token = set_current_rabbitmq_message_headers(
        {AUTH_CONTEXT_SNAPSHOT_HEADER_KEY: "header-snapshot"}
    )
    try:
        with pytest.raises(AuthRequirementDeniedError) as excinfo:
            boundary.seed_auth_context(
                event_type=SampleIntegrationEvent,
                operation="Handler.handle",
                protected=True,
            )
    finally:
        reset_current_rabbitmq_message_headers(token)

    assert excinfo.value.decision == VERIFICATION_PROVIDER_UNAVAILABLE_DECISION


@pytest.mark.parametrize(
    ("error", "decision"),
    [
        (MissingAuthContextSnapshotError(), MISSING_SNAPSHOT_DECISION),
        (InvalidAuthContextSnapshotError(), INVALID_SNAPSHOT_DECISION),
        (ExpiredAuthContextSnapshotError(), EXPIRED_SNAPSHOT_DECISION),
        (
            AuthVerificationProviderUnavailableError(),
            VERIFICATION_PROVIDER_UNAVAILABLE_DECISION,
        ),
    ],
)
def test_seed_auth_context_verifier_errors_expect_decision_mapping(
    error: Exception,
    decision: object,
) -> None:
    """snapshot verifier 오류는 auth decision으로 매핑되어 fail-closed 된다."""
    application_context = ApplicationContext()
    boundary = RabbitMQAuthBoundary(
        application_context,
        RecordingSnapshotVerifier(error),
    )
    token = set_current_rabbitmq_message_headers(
        {AUTH_CONTEXT_SNAPSHOT_HEADER_KEY: "header-snapshot"}
    )
    try:
        with pytest.raises(AuthRequirementDeniedError) as excinfo:
            boundary.seed_auth_context(
                event_type=SampleIntegrationEvent,
                operation="Handler.handle",
                protected=True,
            )
    finally:
        reset_current_rabbitmq_message_headers(token)

    assert excinfo.value.decision == decision


def test_seed_auth_context_metadata_key_precedes_header_key() -> None:
    """metadata key와 header key가 모두 있으면 metadata key를 우선한다."""
    application_context = ApplicationContext()
    verifier = RecordingSnapshotVerifier()
    boundary = RabbitMQAuthBoundary(application_context, verifier)
    headers: Mapping[str, str] = {
        AUTH_CONTEXT_SNAPSHOT_METADATA_KEY: "metadata-snapshot",
        AUTH_CONTEXT_SNAPSHOT_HEADER_KEY: "header-snapshot",
    }
    token = set_current_rabbitmq_message_headers(headers)
    try:
        boundary.seed_auth_context(
            event_type=SampleIntegrationEvent,
            operation="Handler.handle",
            protected=True,
        )
    finally:
        reset_current_rabbitmq_message_headers(token)

    assert verifier.envelope == "metadata-snapshot"
