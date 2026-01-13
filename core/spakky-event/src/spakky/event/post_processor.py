"""Event handler registration post-processor.

This module provides a post-processor that automatically registers
@EventHandler methods with the domain event consumer.
"""

from asyncio import iscoroutinefunction
from inspect import getmembers, ismethod
from logging import getLogger

from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from spakky.domain.models.event import AbstractDomainEvent, AbstractEvent

from spakky.event.event_consumer import (
    IAsyncDomainEventConsumer,
    IDomainEventConsumer,
)
from spakky.event.stereotype.event_handler import EventHandler, EventRoute

logger = getLogger(__name__)


@Pod()
class EventHandlerRegistrationPostProcessor(IPostProcessor, IContainerAware):
    """Post-processor for registering @EventHandler methods with consumers.

    Scans @EventHandler-annotated Pods for methods decorated with @on_event,
    and registers them with the appropriate consumer (sync or async).

    This follows the ISP by depending only on the Consumer interface (registration)
    and not on the Dispatcher interface (event delivery).

    Implements IContainerAware to avoid circular dependency issues during
    initialization by deferring container access to the post_process phase.

    Attributes:
        __container: The IoC container for dependency resolution.
    """

    __container: IContainer

    def set_container(self, container: IContainer) -> None:
        """Set the container for dependency injection.

        Args:
            container: The IoC container.
        """
        self.__container = container

    def post_process(self, pod: object) -> object:
        """Register event handlers from @EventHandler Pod.

        Scans the Pod for methods with @on_event decorator and registers
        them with the appropriate consumer based on whether they are
        coroutine functions or not.

        Args:
            pod: The Pod instance to process.

        Returns:
            The unmodified Pod instance.
        """
        pod_type = type(pod)

        # Only process @EventHandler pods
        if not EventHandler.exists(pod_type):
            return pod

        # Get consumers from container at post-process time to avoid circular dependencies
        sync_consumer = self.__container.get(IDomainEventConsumer)
        async_consumer = self.__container.get(IAsyncDomainEventConsumer)

        # Scan all methods for @on_event decorators
        for name, method in getmembers(pod, predicate=ismethod):
            route = EventRoute[AbstractEvent].get_or_none(method)
            if route is None:
                continue
            if not issubclass(route.event_type, AbstractDomainEvent):
                continue

            event_type = route.event_type

            # Register with appropriate consumer based on async/sync
            if iscoroutinefunction(method):
                async_consumer.register(event_type, method)
                logger.debug(
                    f"Registered async handler {pod_type.__name__}.{name} "
                    f"for {event_type.__name__}"
                )
            else:
                sync_consumer.register(event_type, method)
                logger.debug(
                    f"Registered sync handler {pod_type.__name__}.{name} "
                    f"for {event_type.__name__}"
                )

        return pod
