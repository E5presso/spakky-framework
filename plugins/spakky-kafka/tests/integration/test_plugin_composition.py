"""Actual broker composition with event core, optional mediator and empty consumers."""

from asyncio import to_thread
from queue import Queue
from unittest.mock import AsyncMock, Mock
from typing import ClassVar, override
from uuid import uuid4

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.application.plugin import Plugin
from spakky.core.common.mutability import immutable
from spakky.core.pod.annotations.pod import Pod
from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
)
from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent
from spakky.event.event_consumer import IDomainEventConsumer
from spakky.event.event_publisher import IAsyncEventPublisher, IEventPublisher
from spakky.event.stereotype.event_handler import EventHandler, on_event


@immutable
class LocalChange(AbstractDomainEvent):
    """An aggregate change that must stay in process."""

    value: str


@immutable
class SyncRemoteChange(AbstractIntegrationEvent):
    """A change consumed by a synchronous broker handler."""

    value: str
    topic: ClassVar[str] = "composition.sync"

    @property
    @override
    def event_name(self) -> str:
        """Allow subclasses to vary the topic without redefining the property."""
        return self.topic


@immutable
class AsyncRemoteChange(AbstractIntegrationEvent):
    """A change consumed by an asynchronous broker handler."""

    value: str
    topic: ClassVar[str] = "composition.async"

    @property
    @override
    def event_name(self) -> str:
        """Keep inherited routing identity consistent with publishing."""
        return self.topic


@Pod()
class DeliveryRecorder:
    """Thread-safe native callback observations without timing-based assertions."""

    def __init__(self) -> None:
        """Collect callbacks from native framework service threads."""
        self.deliveries: Queue[tuple[str, str]] = Queue()


@EventHandler()
class LocalHandler:
    """Local handlers selected only when the mediator provider is explicit."""

    def __init__(self, recorder: DeliveryRecorder) -> None:
        """Record actual local callback execution."""
        self.recorder = recorder

    @on_event(LocalChange)
    def synchronous(self, event: LocalChange) -> None:
        """Observe synchronous domain dispatch."""
        self.recorder.deliveries.put(("local-sync", event.value))

    @on_event(LocalChange)
    async def asynchronous(self, event: LocalChange) -> None:
        """Observe asynchronous domain dispatch."""
        self.recorder.deliveries.put(("local-async", event.value))


@Pod()
def transaction() -> AbstractTransaction:
    """Use an explicit transaction test double; these tests change no database state."""
    return Mock(spec=AbstractTransaction)


@Pod()
def async_transaction() -> AbstractAsyncTransaction:
    """Supply the async aspect dependency while broker I/O remains actual."""
    return AsyncMock(spec=AbstractAsyncTransaction)


@pytest.mark.parametrize("local", [False, True])
async def test_native_event_kafka_optional_mediator_expect_actual_broker_delivery(
    monkeypatch, local
):
    """Event+Kafka and Event+Mediator+Kafka route local and external events independently."""
    run_id = uuid4().hex
    monkeypatch.setenv("SPAKKY_KAFKA__GROUP_ID", "composition-" + run_id)

    @immutable
    class ScopedSyncRemoteChange(SyncRemoteChange):
        """One isolated topic using an inherited event_name property."""

        topic: ClassVar[str] = "composition.sync." + run_id

    @immutable
    class ScopedAsyncRemoteChange(AsyncRemoteChange):
        """One isolated async topic using an inherited event_name property."""

        topic: ClassVar[str] = "composition.async." + run_id

    @EventHandler()
    class ScopedRemoteHandler:
        def __init__(self, recorder: DeliveryRecorder) -> None:
            self.recorder = recorder

        @on_event(ScopedSyncRemoteChange)
        def synchronous(self, event: ScopedSyncRemoteChange) -> None:
            self.recorder.deliveries.put(("remote-sync", event.value))

        @on_event(ScopedAsyncRemoteChange)
        async def asynchronous(self, event: ScopedAsyncRemoteChange) -> None:
            self.recorder.deliveries.put(("remote-async", event.value))

    plugins = {
        Plugin(name=name)
        for name in ("spakky-event", "spakky-data", "spakky-tracing", "spakky-kafka")
    }
    if local:
        plugins.add(Plugin(name="spakky-mediator"))
    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(include=plugins)
        .add(transaction)
        .add(async_transaction)
        .add(DeliveryRecorder)
        .add(ScopedRemoteHandler)
    )
    if local:
        app.add(LocalHandler)
    app.start()
    try:
        publisher = app.container.get(IEventPublisher)
        asynchronous = app.container.get(IAsyncEventPublisher)
        value = uuid4().hex
        publisher.publish(ScopedSyncRemoteChange(value=value))
        await asynchronous.publish(ScopedAsyncRemoteChange(value=value))
        expected = {("remote-sync", value), ("remote-async", value)}
        if local:
            publisher.publish(LocalChange(value=value))
            await asynchronous.publish(LocalChange(value=value))
            expected.update({("local-sync", value), ("local-async", value)})
        else:
            assert app.container.get_or_none(IDomainEventConsumer) is None
        recorder = app.container.get(DeliveryRecorder)
        received = {
            await to_thread(recorder.deliveries.get, timeout=10) for _ in expected
        }
        assert received == expected
    finally:
        app.stop()


def test_native_producer_only_kafka_expect_empty_consumer_start_and_stop(monkeypatch):
    """No placeholder handler is needed for a publishing-only application's lifecycle."""
    monkeypatch.setenv("SPAKKY_KAFKA__GROUP_ID", "producer-only-" + uuid4().hex)
    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(
            include={
                Plugin(name=name)
                for name in (
                    "spakky-event",
                    "spakky-data",
                    "spakky-tracing",
                    "spakky-kafka",
                )
            }
        )
        .add(transaction)
        .add(async_transaction)
    )
    app.start()
    try:
        assert app.container.get_or_none(IDomainEventConsumer) is None
        assert app.container.get(IEventPublisher) is not None
    finally:
        app.stop()
