"""Event handler registration post-processor."""

from logging import getLogger
from typing import override

from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from spakky.domain.models.event import AbstractDomainEvent

from spakky.event.event_consumer import (
    IAsyncDomainEventConsumer,
    IDomainEventConsumer,
)
from spakky.event.stereotype.event_handler import EventHandler

logger = getLogger(__name__)


@Pod()
class EventHandlerRegistrationPostProcessor(IPostProcessor, IContainerAware):
    """Scans @EventHandler Pods and registers their @on_event methods with consumers."""

    __container: IContainer

    @override
    def set_container(self, container: IContainer) -> None:
        """Receive the container reference via IContainerAware."""
        self.__container = container

    @override
    def post_process(self, pod: object) -> object:
        """Register event handler methods with the appropriate consumer."""
        pod_type = type(pod)

        if not EventHandler.exists(pod_type):
            return pod

        sync_consumer = self.__container.get(IDomainEventConsumer)
        async_consumer = self.__container.get(IAsyncDomainEventConsumer)

        # Routes are read from the class: an advised Pod is an AOP proxy whose
        # attributes are not bound methods, so scanning the instance would skip it.
        for declared in EventHandler.get(pod_type).routes():
            route = declared.route
            name = declared.method_name
            if not issubclass(route.event_type, AbstractDomainEvent):
                continue
            method = getattr(  # event handler method lookup
                pod, name
            )  # 프레임워크 내부: 선언된 이름으로 (프록시된) 처리기 메서드를 찾는다

            event_type = route.event_type

            if declared.asynchronous:
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
