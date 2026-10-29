"""Missing handler providers fail at startup without selecting hidden consumers."""

from unittest.mock import Mock

import pytest
from spakky.core.common.mutability import immutable
from spakky.core.pod.interfaces.container import IContainer
from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent

from spakky.event.error import EventHandlerProviderUnavailableError
from spakky.event.event_consumer import (
    IAsyncDomainEventConsumer,
    IAsyncIntegrationEventConsumer,
    IDomainEventConsumer,
    IIntegrationEventConsumer,
)
from spakky.event.post_processor import EventHandlerProviderValidationPostProcessor
from spakky.event.stereotype.event_handler import EventHandler, on_event


@immutable
class LocalChange(AbstractDomainEvent):
    """A local aggregate change."""

    value: str


@immutable
class RemoteChange(AbstractIntegrationEvent):
    """A cross-service change."""

    value: str


@pytest.mark.parametrize(
    "event_type, asynchronous, provider_type",
    [
        (LocalChange, False, IDomainEventConsumer),
        (LocalChange, True, IAsyncDomainEventConsumer),
        (RemoteChange, False, IIntegrationEventConsumer),
        (RemoteChange, True, IAsyncIntegrationEventConsumer),
    ],
)
@pytest.mark.parametrize("available", [True, False])
def test_declared_handler_provider_validation_expect_exact_role(
    event_type, asynchronous, provider_type, available
):
    """Each domain/integration and sync/async route needs its own capability."""
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

    registry = Mock(spec=IContainer)
    registry.get_or_none.return_value = Mock() if available else None
    processor = EventHandlerProviderValidationPostProcessor()
    processor.set_container(registry)
    handler = Handler()
    if available:
        assert processor.post_process(handler) is handler
    else:
        with pytest.raises(EventHandlerProviderUnavailableError) as caught:
            processor.post_process(handler)
        assert caught.value.provider_type is provider_type
        assert caught.value.event_type is event_type
        assert caught.value.handler.endswith("Handler.receive")
    registry.get_or_none.assert_called_once_with(provider_type)


def test_unannotated_methods_and_objects_expect_no_provider_requirement():
    """Ordinary Pods and helpers do not require an event provider installation."""

    @EventHandler()
    class Handler:
        def helper(self):
            return "ordinary"

    registry = Mock(spec=IContainer)
    processor = EventHandlerProviderValidationPostProcessor()
    processor.set_container(registry)
    ordinary = object()
    assert processor.post_process(ordinary) is ordinary
    handler = Handler()
    assert processor.post_process(handler) is handler
    registry.get_or_none.assert_not_called()


def test_unclassified_event_handler_expect_explicit_unsupported_type_error():
    """A route must declare domain or integration semantics instead of being ignored."""
    from spakky.domain.models.event import AbstractEvent
    from spakky.event.error import UnknownEventTypeError

    @immutable
    class Unclassified(AbstractEvent):
        value: str

    @EventHandler()
    class Handler:
        @on_event(Unclassified)
        def receive(self, event):
            del event

    processor = EventHandlerProviderValidationPostProcessor()
    processor.set_container(Mock(spec=IContainer))
    with pytest.raises(UnknownEventTypeError) as caught:
        processor.post_process(Handler())
    assert caught.value.event_type is Unclassified
