"""Fail startup when declared handlers lack an explicit consumer provider."""

from inspect import getmembers, iscoroutinefunction, ismethod
from typing import override

from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent

from spakky.event.error import (
    EventHandlerProviderUnavailableError,
    UnknownEventTypeError,
)
from spakky.event.event_consumer import (
    IAsyncDomainEventConsumer,
    IAsyncIntegrationEventConsumer,
    IDomainEventConsumer,
    IIntegrationEventConsumer,
)
from spakky.event.stereotype.event_handler import EventHandler, EventRoute


@Pod()
class EventHandlerProviderValidationPostProcessor(IPostProcessor, IContainerAware):
    """Validate domain/integration and sync/async capabilities without a hidden provider."""

    _container: IContainer

    @override
    def set_container(self, container: IContainer) -> None:
        """Receive the provider-neutral registry for startup validation.

        Args:
            container: Registry containing only explicitly selected providers.
        """
        self._container = container

    @override
    def post_process(self, pod: object) -> object:
        """Fail deterministically when a declared handler would remain unregistered.

        Args:
            pod: Constructed business or infrastructure Pod.

        Returns:
            The original Pod after validating all declared event routes.

        Raises:
            EventHandlerProviderUnavailableError: No provider supports the handler role.
        """
        if not EventHandler.exists(type(pod)):
            return pod
        for name, method in getmembers(pod, predicate=ismethod):
            route = EventRoute.get_or_none(method)
            if route is None:
                continue
            asynchronous = iscoroutinefunction(method)
            if issubclass(route.event_type, AbstractDomainEvent):
                provider = (
                    IAsyncDomainEventConsumer if asynchronous else IDomainEventConsumer
                )
            elif issubclass(route.event_type, AbstractIntegrationEvent):
                provider = (
                    IAsyncIntegrationEventConsumer
                    if asynchronous
                    else IIntegrationEventConsumer
                )
            else:
                raise UnknownEventTypeError(route.event_type)
            if self._container.get_or_none(provider) is None:
                raise EventHandlerProviderUnavailableError(
                    f"{type(pod).__module__}.{type(pod).__qualname__}.{name}",
                    route.event_type,
                    provider,
                )
        return pod
