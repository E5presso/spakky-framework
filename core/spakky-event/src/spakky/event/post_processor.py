"""Fail startup when declared handlers lack an explicit consumer provider."""

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
from spakky.event.stereotype.event_handler import EventHandler
from spakky.event.subscription import MixedSubscriptionModeError, SubscriberName


@Pod()
class EventHandlerProviderValidationPostProcessor(IPostProcessor, IContainerAware):
    """Validate domain/integration and sync/async capabilities without a hidden provider."""

    _container: IContainer
    _subscription_modes: dict[tuple[SubscriberName | None, type], bool]
    """Whether each integration subscription seen so far is asynchronous."""

    def __init__(self) -> None:
        self._subscription_modes = {}

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
            MixedSubscriptionModeError: One subscription mixes sync and async handlers.
        """
        if not EventHandler.exists(type(pod)):
            return pod
        handler = EventHandler.get(type(pod))
        for declared in handler.routes():
            route = declared.route
            if issubclass(route.event_type, AbstractDomainEvent):
                provider = (
                    IAsyncDomainEventConsumer
                    if declared.asynchronous
                    else IDomainEventConsumer
                )
            elif issubclass(route.event_type, AbstractIntegrationEvent):
                provider = (
                    IAsyncIntegrationEventConsumer
                    if declared.asynchronous
                    else IIntegrationEventConsumer
                )
                subscription = (handler.subscriber, route.event_type)
                known = self._subscription_modes.setdefault(
                    subscription, declared.asynchronous
                )
                if known is not declared.asynchronous:
                    raise MixedSubscriptionModeError(*subscription)
            else:
                raise UnknownEventTypeError(route.event_type)
            if self._container.get_or_none(provider) is None:
                raise EventHandlerProviderUnavailableError(
                    f"{handler.type_.__module__}.{handler.type_.__qualname__}."
                    f"{declared.method_name}",
                    route.event_type,
                    provider,
                )
        return pod
