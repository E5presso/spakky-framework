"""Native event-only startup provides contracts and fails unsupported publishing explicitly."""

from unittest.mock import AsyncMock, Mock

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

from spakky.event.error import (
    DomainEventDispatcherUnavailableError,
    IntegrationEventTransportUnavailableError,
)
from spakky.event.event_consumer import IAsyncEventConsumer, IEventConsumer
from spakky.event.event_publisher import IAsyncEventPublisher, IEventPublisher


@Pod()
def transaction() -> AbstractTransaction:
    """Provide an explicit transaction test double for an infrastructure-free contract test."""
    return Mock(spec=AbstractTransaction)


@Pod()
def async_transaction() -> AbstractAsyncTransaction:
    """Provide the async transaction test double required by publishing aspects."""
    return AsyncMock(spec=AbstractAsyncTransaction)


@immutable
class LocalChange(AbstractDomainEvent):
    """Local publishing needs an explicitly installed mediator provider."""

    value: str


@immutable
class RemoteChange(AbstractIntegrationEvent):
    """External publishing needs an explicitly installed broker provider."""

    value: str


async def test_event_only_native_startup_expect_no_hidden_consumer():
    """The event contract plugin starts without selecting any local or external consumer."""
    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(
            include={
                Plugin(name="spakky-event"),
                Plugin(name="spakky-data"),
                Plugin(name="spakky-tracing"),
            }
        )
        .add(transaction)
        .add(async_transaction)
    )
    app.start()
    try:
        assert app.container.get_or_none(IEventConsumer) is None
        assert app.container.get_or_none(IAsyncEventConsumer) is None
        publisher = app.container.get(IEventPublisher)
        asynchronous = app.container.get(IAsyncEventPublisher)
        with pytest.raises(DomainEventDispatcherUnavailableError):
            publisher.publish(LocalChange(value="no mediator"))
        with pytest.raises(DomainEventDispatcherUnavailableError):
            await asynchronous.publish(LocalChange(value="no mediator"))
        with pytest.raises(IntegrationEventTransportUnavailableError):
            publisher.publish(RemoteChange(value="no broker"))
        with pytest.raises(IntegrationEventTransportUnavailableError):
            await asynchronous.publish(RemoteChange(value="no broker"))
    finally:
        app.stop()


@pytest.mark.parametrize(
    "event_type, asynchronous",
    [
        (LocalChange, False),
        (LocalChange, True),
        (RemoteChange, False),
        (RemoteChange, True),
    ],
)
def test_native_startup_without_handler_provider_expect_configuration_failure(
    event_type, asynchronous
):
    """Native startup rejects a declared unsupported handler before any event can be lost."""
    from spakky.event.error import EventHandlerProviderUnavailableError
    from spakky.event.stereotype.event_handler import EventHandler, on_event

    if asynchronous:

        @EventHandler()
        class Handler:
            @on_event(event_type)
            async def receive(self, event):
                del event
    else:

        @EventHandler()
        class Handler:
            @on_event(event_type)
            def receive(self, event):
                del event

    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(
            include={
                Plugin(name="spakky-event"),
                Plugin(name="spakky-data"),
                Plugin(name="spakky-tracing"),
            }
        )
        .add(transaction)
        .add(async_transaction)
        .add(Handler)
    )
    with pytest.raises(EventHandlerProviderUnavailableError) as caught:
        app.start()
    assert caught.value.event_type is event_type
    assert caught.value.handler.endswith("Handler.receive")
