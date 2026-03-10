"""Event handler registration post-processor."""

from inspect import getmembers, iscoroutinefunction, ismethod
from logging import getLogger

from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from spakky.domain.models.event import AbstractDomainEvent, AbstractEvent

from spakky.event.event_consumer import (
    IAsyncEventConsumer,
    IEventConsumer,
)
from spakky.event.stereotype.event_handler import EventHandler, EventRoute

logger = getLogger(__name__)


@Pod()
class EventHandlerRegistrationPostProcessor(IPostProcessor, IContainerAware):
    __container: IContainer

    def set_container(self, container: IContainer) -> None:
        self.__container = container

    def post_process(self, pod: object) -> object:
        pod_type = type(pod)

        if not EventHandler.exists(pod_type):
            return pod

        sync_consumer = self.__container.get(IEventConsumer)
        async_consumer = self.__container.get(IAsyncEventConsumer)

        for name, method in getmembers(pod, predicate=ismethod):
            route = EventRoute[AbstractEvent].get_or_none(method)
            if route is None:
                continue
            if not issubclass(route.event_type, AbstractDomainEvent):
                continue

            event_type = route.event_type

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
