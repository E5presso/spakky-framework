"""Post-processor for registering RabbitMQ event handlers.

Automatically discovers and registers event handlers from @EventHandler
decorated classes, connecting them to RabbitMQ consumers with dependency injection.
"""

from functools import wraps
from inspect import getmembers, iscoroutinefunction, ismethod
from logging import Logger
from typing import Any

from spakky.domain.models.event import AbstractDomainEvent
from spakky.domain.ports.event.event_consumer import IAsyncEventConsumer, IEventConsumer
from spakky.pod.annotations.order import Order
from spakky.pod.annotations.pod import Pod
from spakky.pod.interfaces.application_context import IApplicationContext
from spakky.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.pod.interfaces.aware.container_aware import IContainerAware
from spakky.pod.interfaces.aware.logger_aware import ILoggerAware
from spakky.pod.interfaces.container import IContainer
from spakky.pod.interfaces.post_processor import IPostProcessor
from spakky.stereotype.event_handler import EventHandler, EventRoute


@Order(1)
@Pod()
class RabbitMQPostProcessor(
    IPostProcessor, ILoggerAware, IContainerAware, IApplicationContextAware
):
    """Post-processor that registers event handlers with RabbitMQ consumers.

    Scans @EventHandler decorated classes for @event decorated methods and
    automatically registers them with the appropriate RabbitMQ consumer
    (sync or async) with proper dependency injection.
    """

    __logger: Logger
    __container: IContainer
    __application_context: IApplicationContext

    def set_logger(self, logger: Logger) -> None:
        """Set the logger for event handler registration logging.

        Args:
            logger: The logger instance.
        """
        self.__logger = logger

    def set_container(self, container: IContainer) -> None:
        """Set the container for dependency injection.

        Args:
            container: The IoC container.
        """
        self.__container = container

    def set_application_context(self, application_context: IApplicationContext) -> None:
        """Set the application context.

        Args:
            application_context: The application context instance.
        """
        self.__application_context = application_context

    def post_process(self, pod: object) -> object:
        """Register event handlers from event handler classes.

        Scans the event handler for methods decorated with @event and registers
        them with the appropriate RabbitMQ consumer (sync or async) based on
        whether the method is a coroutine function.

        Args:
            pod: The Pod to process, potentially an event handler.

        Returns:
            The Pod, with event handlers registered if it's an event handler.
        """
        if not EventHandler.exists(pod):
            return pod
        handler: EventHandler = EventHandler.get(pod)
        consumer = self.__container.get(IEventConsumer)
        async_consumer = self.__container.get(IAsyncEventConsumer)
        for name, method in getmembers(pod, ismethod):
            route: EventRoute[AbstractDomainEvent] | None = EventRoute[
                AbstractDomainEvent
            ].get_or_none(method)
            if route is None:
                continue
            # pylint: disable=line-too-long
            self.__logger.info(
                f"[{type(self).__name__}] {route.event_type.__name__} -> {method.__qualname__}"
            )

            if iscoroutinefunction(method):

                @wraps(method)
                async def async_endpoint(
                    *args: Any,
                    method_name: str = name,
                    controller_type: type[object] = handler.type_,
                    context: IContainer = self.__container,
                    **kwargs: Any,
                ) -> Any:
                    # Each message is handled in isolation, so clear the
                    # application context to avoid reusing dependency state.
                    self.__application_context.clear_context()
                    controller_instance = context.get(controller_type)
                    method_to_call = getattr(controller_instance, method_name)
                    return await method_to_call(*args, **kwargs)

                async_consumer.register(route.event_type, async_endpoint)
                continue

            @wraps(method)
            def endpoint(
                *args: Any,
                method_name: str = name,
                controller_type: type[object] = handler.type_,
                context: IContainer = self.__container,
                **kwargs: Any,
            ) -> Any:
                # Synchronous consumers share threads, so drop any lingering
                # scoped data before invoking the handler.
                self.__application_context.clear_context()
                controller_instance = context.get(controller_type)
                method_to_call = getattr(controller_instance, method_name)
                return method_to_call(*args, **kwargs)

            consumer.register(route.event_type, endpoint)
        return pod
