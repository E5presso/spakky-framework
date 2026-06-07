"""Unit tests for DirectEventBus/AsyncDirectEventBus trace propagation."""

from datetime import UTC, datetime, timedelta
from typing import override

import pytest
from spakky.auth import (
    AUTH_CONTEXT_SNAPSHOT_METADATA_KEY,
    AuthContext,
    AuthContextSnapshot,
    AuthContextSnapshotSignature,
    AuthSnapshotPropagationConfig,
    AuthSubject,
    CredentialCarrier,
    CredentialCarrierKind,
    CredentialCarrierLocation,
    IAuthContextSnapshotSigner,
    SnapshotSignRequest,
    store_auth_context,
)
from spakky.core.application.application_context import ApplicationContext
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.tracing.context import TraceContext
from spakky.tracing.propagator import ITracePropagator

from spakky.event.auth_propagation import AuthContextSnapshotHeaderInjector
from spakky.event.bus.transport_event_bus import AsyncDirectEventBus, DirectEventBus
from spakky.event.event_publisher import IAsyncEventTransport, IEventTransport


@immutable
class SampleIntegrationEvent(AbstractIntegrationEvent):
    """Sample integration event for testing."""

    message: str


class RecordingTransport(IEventTransport):
    """Transport that records sent events with headers."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, dict[str, str]]] = []

    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        self.sent.append((event_name, payload, headers))


class AsyncRecordingTransport(IAsyncEventTransport):
    """Async transport that records sent events with headers."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, dict[str, str]]] = []

    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        self.sent.append((event_name, payload, headers))


class FakePropagator(ITracePropagator):
    """Fake propagator that injects a fixed traceparent header."""

    def inject(self, carrier: dict[str, str]) -> None:
        carrier["traceparent"] = (
            "00-abcd1234abcd1234abcd1234abcd1234-1234abcd1234abcd-01"
        )

    def extract(self, carrier: dict[str, str]) -> TraceContext | None:
        return None

    def fields(self) -> list[str]:
        return ["traceparent"]


class BearerInjectingPropagator(FakePropagator):
    """Fake propagator that also tries to inject a raw bearer header."""

    @override
    def inject(self, carrier: dict[str, str]) -> None:
        super().inject(carrier)
        carrier["authorization"] = "Bearer raw-token"


class FakeSnapshotSigner(IAuthContextSnapshotSigner):
    """Signer that records requests and returns a deterministic snapshot."""

    def __init__(self) -> None:
        self.requests: list[SnapshotSignRequest] = []

    @override
    def sign_snapshot(self, request: SnapshotSignRequest) -> AuthContextSnapshot:
        self.requests.append(request)
        return AuthContextSnapshot(
            subject=request.auth_context.subject,
            issuer=request.auth_context.issuer,
            issued_at=datetime(2026, 1, 1, tzinfo=UTC),
            expires_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=5),
            signature=AuthContextSnapshotSignature(
                key_id="kid-1",
                algorithm="HS256",
                signature="signature-1",
            ),
            tenant=request.auth_context.tenant,
            roles=request.auth_context.roles,
            scopes=request.auth_context.scopes,
            selected_claims=request.auth_context.claims,
        )


def _auth_context() -> AuthContext:
    return AuthContext(
        subject=AuthSubject(id="subject-1", display_name="Subject One"),
        issuer="issuer-1",
        tenant="tenant-1",
        roles=("role-1",),
        scopes=("scope-1",),
        credential_carrier=CredentialCarrier(
            kind=CredentialCarrierKind.BEARER_TOKEN,
            location=CredentialCarrierLocation.AUTHORIZATION_HEADER,
            material="raw-token",
            name="authorization",
            scheme="Bearer",
        ),
    )


def _enabled_auth_headers(
    signer: FakeSnapshotSigner,
) -> AuthContextSnapshotHeaderInjector:
    application_context = ApplicationContext()
    store_auth_context(application_context, _auth_context())
    injector = AuthContextSnapshotHeaderInjector(
        auth_snapshot_signer=signer,
        auth_snapshot_propagation_config=AuthSnapshotPropagationConfig(enabled=True),
    )
    injector.set_application_context(application_context)
    return injector


# ── Sync tests ──


def test_direct_event_bus_with_propagator_expect_headers_injected() -> None:
    """propagator가 있을 때 transport.send에 traceparent 헤더가 포함됨을 검증한다."""
    transport = RecordingTransport()
    propagator = FakePropagator()
    bus = DirectEventBus(transport, propagator)

    event = SampleIntegrationEvent(message="traced")
    bus.send(event)

    assert len(transport.sent) == 1
    _, _, headers = transport.sent[0]
    assert headers is not None
    assert "traceparent" in headers
    assert (
        headers["traceparent"]
        == "00-abcd1234abcd1234abcd1234abcd1234-1234abcd1234abcd-01"
    )


def test_direct_event_bus_with_auth_context_expect_signed_snapshot_metadata() -> None:
    """sync event bus가 trace header를 보존하고 signed snapshot만 전파함을 검증한다."""
    transport = RecordingTransport()
    signer = FakeSnapshotSigner()
    bus = DirectEventBus(
        transport,
        BearerInjectingPropagator(),
        _enabled_auth_headers(signer),
    )

    event = SampleIntegrationEvent(message="signed")
    bus.send(event)

    assert len(signer.requests) == 1
    _, _, headers = transport.sent[0]
    assert "traceparent" in headers
    assert AUTH_CONTEXT_SNAPSHOT_METADATA_KEY in headers
    assert "authorization" not in headers
    assert all("raw-token" not in value for value in headers.values())


# ── Async tests ──


@pytest.mark.asyncio
async def test_async_direct_event_bus_with_propagator_expect_headers_injected() -> None:
    """async propagator가 있을 때 transport.send에 traceparent 헤더가 포함됨을 검증한다."""
    transport = AsyncRecordingTransport()
    propagator = FakePropagator()
    bus = AsyncDirectEventBus(transport, propagator)

    event = SampleIntegrationEvent(message="async-traced")
    await bus.send(event)

    assert len(transport.sent) == 1
    _, _, headers = transport.sent[0]
    assert headers is not None
    assert "traceparent" in headers
    assert (
        headers["traceparent"]
        == "00-abcd1234abcd1234abcd1234abcd1234-1234abcd1234abcd-01"
    )


@pytest.mark.asyncio
async def test_async_direct_event_bus_with_auth_context_expect_signed_snapshot_metadata() -> (
    None
):
    """async event bus가 trace header를 보존하고 signed snapshot만 전파함을 검증한다."""
    transport = AsyncRecordingTransport()
    signer = FakeSnapshotSigner()
    bus = AsyncDirectEventBus(
        transport,
        BearerInjectingPropagator(),
        _enabled_auth_headers(signer),
    )

    event = SampleIntegrationEvent(message="async-signed")
    await bus.send(event)

    assert len(signer.requests) == 1
    _, _, headers = transport.sent[0]
    assert "traceparent" in headers
    assert AUTH_CONTEXT_SNAPSHOT_METADATA_KEY in headers
    assert "authorization" not in headers
    assert all("raw-token" not in value for value in headers.values())
