"""Tests for OutboxEventBus and AsyncOutboxEventBus."""

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
from spakky.tracing import W3CTracePropagator
from spakky.tracing.context import TraceContext
from spakky.tracing.propagator import ITracePropagator

from spakky.event.auth_propagation import AuthContextSnapshotHeaderInjector
from spakky.outbox.bus.outbox_event_bus import (
    AsyncOutboxEventBus,
    OutboxEventBus,
)
from spakky.outbox.common.message import OutboxMessage
from spakky.outbox.ports.storage import IAsyncOutboxStorage, IOutboxStorage


@immutable
class OrderConfirmedIntegrationEvent(AbstractIntegrationEvent):
    order_id: str
    amount: int


class InMemorySyncOutboxStorage(IOutboxStorage):
    def __init__(self) -> None:
        self.saved: list[OutboxMessage] = []

    def save(self, message: OutboxMessage) -> None:
        self.saved.append(message)

    def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
        raise AssertionError("Not expected to be called")

    def mark_published(self, message_id: object) -> None:
        raise AssertionError("Not expected to be called")

    def increment_retry(self, message_id: object) -> None:
        raise AssertionError("Not expected to be called")


class InMemoryAsyncOutboxStorage(IAsyncOutboxStorage):
    def __init__(self) -> None:
        self.saved: list[OutboxMessage] = []

    async def save(self, message: OutboxMessage) -> None:
        self.saved.append(message)

    async def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
        raise AssertionError("Not expected to be called")

    async def mark_published(self, message_id: object) -> None:
        raise AssertionError("Not expected to be called")

    async def increment_retry(self, message_id: object) -> None:
        raise AssertionError("Not expected to be called")


class BearerInjectingPropagator(ITracePropagator):
    """Fake propagator that injects tracing and raw bearer material."""

    @override
    def inject(self, carrier: dict[str, str]) -> None:
        carrier["traceparent"] = (
            "00-abcd1234abcd1234abcd1234abcd1234-1234abcd1234abcd-01"
        )
        carrier["authorization"] = "Bearer raw-token"

    @override
    def extract(self, carrier: dict[str, str]) -> TraceContext | None:
        return None

    @override
    def fields(self) -> list[str]:
        return ["traceparent"]


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


# ── Sync OutboxEventBus ──


def test_send_stores_message_in_outbox_storage() -> None:
    """OutboxEventBus.send가 이벤트를 OutboxMessage로 변환하여 저장소에 저장하는지 검증한다."""
    storage = InMemorySyncOutboxStorage()
    bus = OutboxEventBus(storage, W3CTracePropagator())

    event = OrderConfirmedIntegrationEvent(order_id="ORD-001", amount=5000)
    bus.send(event)

    assert len(storage.saved) == 1
    message = storage.saved[0]
    assert message.event_name == "OrderConfirmedIntegrationEvent"
    assert message.published_at is None
    assert message.retry_count == 0
    assert len(message.payload) > 0


def test_send_serializes_event_payload_as_json() -> None:
    """OutboxEventBus.send가 이벤트 payload를 JSON bytes로 직렬화하는지 검증한다."""
    storage = InMemorySyncOutboxStorage()
    bus = OutboxEventBus(storage, W3CTracePropagator())

    event = OrderConfirmedIntegrationEvent(order_id="ORD-002", amount=3000)
    bus.send(event)

    message = storage.saved[0]
    payload_str = message.payload.decode("utf-8")
    assert "ORD-002" in payload_str
    assert "3000" in payload_str


def test_send_generates_unique_message_ids() -> None:
    """OutboxEventBus.send가 각 메시지에 고유한 ID를 부여하는지 검증한다."""
    storage = InMemorySyncOutboxStorage()
    bus = OutboxEventBus(storage, W3CTracePropagator())

    event1 = OrderConfirmedIntegrationEvent(order_id="ORD-A", amount=100)
    event2 = OrderConfirmedIntegrationEvent(order_id="ORD-B", amount=200)
    bus.send(event1)
    bus.send(event2)

    assert len(storage.saved) == 2
    assert storage.saved[0].id != storage.saved[1].id


def test_send_stores_signed_snapshot_metadata_in_headers() -> None:
    """OutboxEventBus가 trace를 보존하고 signed snapshot만 저장함을 검증한다."""
    storage = InMemorySyncOutboxStorage()
    signer = FakeSnapshotSigner()
    bus = OutboxEventBus(
        storage,
        BearerInjectingPropagator(),
        _enabled_auth_headers(signer),
    )

    event = OrderConfirmedIntegrationEvent(order_id="ORD-AUTH", amount=7000)
    bus.send(event)

    assert len(signer.requests) == 1
    headers = storage.saved[0].headers
    assert "traceparent" in headers
    assert AUTH_CONTEXT_SNAPSHOT_METADATA_KEY in headers
    assert "authorization" not in headers
    assert all("raw-token" not in value for value in headers.values())


# ── Async AsyncOutboxEventBus ──


@pytest.mark.asyncio
async def test_async_send_stores_message_in_outbox_storage() -> None:
    """AsyncOutboxEventBus.send가 이벤트를 OutboxMessage로 변환하여 저장소에 저장하는지 검증한다."""
    storage = InMemoryAsyncOutboxStorage()
    bus = AsyncOutboxEventBus(storage, W3CTracePropagator())

    event = OrderConfirmedIntegrationEvent(order_id="ORD-001", amount=5000)
    await bus.send(event)

    assert len(storage.saved) == 1
    message = storage.saved[0]
    assert message.event_name == "OrderConfirmedIntegrationEvent"
    assert message.published_at is None
    assert message.retry_count == 0
    assert len(message.payload) > 0


@pytest.mark.asyncio
async def test_async_send_serializes_event_payload_as_json() -> None:
    """AsyncOutboxEventBus.send가 이벤트 payload를 JSON bytes로 직렬화하는지 검증한다."""
    storage = InMemoryAsyncOutboxStorage()
    bus = AsyncOutboxEventBus(storage, W3CTracePropagator())

    event = OrderConfirmedIntegrationEvent(order_id="ORD-002", amount=3000)
    await bus.send(event)

    message = storage.saved[0]
    payload_str = message.payload.decode("utf-8")
    assert "ORD-002" in payload_str
    assert "3000" in payload_str


@pytest.mark.asyncio
async def test_async_send_generates_unique_message_ids() -> None:
    """AsyncOutboxEventBus.send가 각 메시지에 고유한 ID를 부여하는지 검증한다."""
    storage = InMemoryAsyncOutboxStorage()
    bus = AsyncOutboxEventBus(storage, W3CTracePropagator())

    event1 = OrderConfirmedIntegrationEvent(order_id="ORD-A", amount=100)
    event2 = OrderConfirmedIntegrationEvent(order_id="ORD-B", amount=200)
    await bus.send(event1)
    await bus.send(event2)

    assert len(storage.saved) == 2
    assert storage.saved[0].id != storage.saved[1].id


@pytest.mark.asyncio
async def test_async_send_stores_signed_snapshot_metadata_in_headers() -> None:
    """AsyncOutboxEventBus가 trace를 보존하고 signed snapshot만 저장함을 검증한다."""
    storage = InMemoryAsyncOutboxStorage()
    signer = FakeSnapshotSigner()
    bus = AsyncOutboxEventBus(
        storage,
        BearerInjectingPropagator(),
        _enabled_auth_headers(signer),
    )

    event = OrderConfirmedIntegrationEvent(order_id="ORD-ASYNC-AUTH", amount=8000)
    await bus.send(event)

    assert len(signer.requests) == 1
    headers = storage.saved[0].headers
    assert "traceparent" in headers
    assert AUTH_CONTEXT_SNAPSHOT_METADATA_KEY in headers
    assert "authorization" not in headers
    assert all("raw-token" not in value for value in headers.values())
