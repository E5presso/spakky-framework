from functools import wraps
from inspect import getmembers, iscoroutinefunction, ismethod
from logging import getLogger
from typing import Any

from spakky.auth import AuthorizationDecisionState, get_effective_auth_metadata
from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from spakky.domain.models.event import AbstractEvent, AbstractIntegrationEvent
from spakky.event.event_consumer import (
    IAsyncEventConsumer,
    IEventConsumer,
)
from spakky.event.stereotype.event_handler import EventHandler, EventRoute
from spakky.tracing.propagator import ITracePropagator
from typing import override

from spakky.plugins.kafka.auth import (
    KafkaAuthBoundary,
    KafkaHandlerAuthBinding,
)

logger = getLogger(__name__)


@Order(1)
@Pod()
class KafkaPostProcessor(IPostProcessor, IContainerAware, IApplicationContextAware):
    """Post-processor that registers event handlers with Kafka consumers.

    Scans @EventHandler decorated classes for @event decorated methods and
    automatically registers them with the appropriate Kafka consumer
    (sync or async) with proper dependency injection.
    """

    __container: IContainer
    __application_context: IApplicationContext

    @override
    def set_container(self, container: IContainer) -> None:
        """Set the container for dependency injection.

        Args:
            container: The IoC container.
        """
        self.__container = container

    @override
    def set_application_context(self, application_context: IApplicationContext) -> None:
        """Set the application context.

        Args:
            application_context: The application context instance.
        """
        self.__application_context = application_context

    @override
    def post_process(self, pod: object) -> object:
        """Register event handlers from event handler classes.

        Scans the event handler for methods decorated with @on_event and registers
        them with the appropriate Kafka consumer (sync or async) based on
        whether the method is a coroutine function.

        Args:
            pod: The Pod to process.

        Returns:
            The Pod, with event handlers registered if it's an event handler.
        """
        if not EventHandler.exists(pod):
            return pod
        handler: EventHandler = EventHandler.get(pod)
        consumer = self.__container.get(IEventConsumer)
        async_consumer = self.__container.get(IAsyncEventConsumer)
        auth_boundary = KafkaAuthBoundary(self.__container, self.__application_context)
        propagator = self.__application_context.get_or_none(ITracePropagator)
        if propagator is not None:
            if hasattr(  # optional tracing bridge injection
                consumer, "set_propagator"
            ):  # 프레임워크 내부: consumer가 선택적 propagator를 지원하는지 확인
                consumer.set_propagator(propagator)
            if hasattr(  # optional tracing bridge injection
                async_consumer, "set_propagator"
            ):  # 프레임워크 내부: consumer가 선택적 propagator를 지원하는지 확인
                async_consumer.set_propagator(propagator)
        for name, method in getmembers(pod, ismethod):
            route: EventRoute[AbstractEvent] | None = EventRoute[
                AbstractEvent
            ].get_or_none(method)
            if route is None:
                continue
            if not issubclass(route.event_type, AbstractIntegrationEvent):
                continue

            # pylint: disable=line-too-long
            logger.info(
                f"[{type(self).__name__}] {route.event_type.__name__} -> {method.__qualname__}"
            )
            auth_metadata = get_effective_auth_metadata(
                method,
                owner_type=handler.type_,
            )
            auth_binding = KafkaHandlerAuthBinding(
                operation=f"{handler.type_.__module__}.{handler.type_.__qualname__}.{name}",
                protected=auth_metadata.protected,
            )

            if iscoroutinefunction(method):

                @wraps(method)
                async def async_endpoint(
                    *args: Any,
                    _spakky_kafka_headers: dict[str, str] | None = None,
                    method_name: str = name,
                    controller_type: type[object] = handler.type_,
                    context: IContainer = self.__container,
                    boundary: KafkaAuthBoundary = auth_boundary,
                    binding: KafkaHandlerAuthBinding = auth_binding,
                    **kwargs: Any,
                ) -> Any:
                    # Each message is handled in isolation, so clear the
                    # application context to avoid reusing dependency state.
                    self.__application_context.clear_context()
                    decision = boundary.seed_auth_context(
                        _spakky_kafka_headers or {},
                        binding,
                    )
                    if decision.state is not AuthorizationDecisionState.ALLOW:
                        return None
                    controller_instance = context.get(controller_type)
                    method_to_call = getattr(  # event handler method lookup
                        controller_instance, method_name
                    )  # 프레임워크 내부: 이벤트 핸들러 메서드 동적 디스패치
                    return await method_to_call(*args, **kwargs)

                async_consumer.register(route.event_type, async_endpoint)
                if hasattr(  # optional auth-aware Kafka consumer bridge
                    async_consumer,
                    "register_auth_boundary",
                ):
                    async_consumer.register_auth_boundary(async_endpoint)
                continue

            @wraps(method)
            def endpoint(
                *args: Any,
                _spakky_kafka_headers: dict[str, str] | None = None,
                method_name: str = name,
                controller_type: type[object] = handler.type_,
                context: IContainer = self.__container,
                boundary: KafkaAuthBoundary = auth_boundary,
                binding: KafkaHandlerAuthBinding = auth_binding,
                **kwargs: Any,
            ) -> Any:
                # Synchronous consumers share threads, so drop any lingering
                # scoped data before invoking the handler.
                self.__application_context.clear_context()
                decision = boundary.seed_auth_context(
                    _spakky_kafka_headers or {},
                    binding,
                )
                if decision.state is not AuthorizationDecisionState.ALLOW:
                    return None
                controller_instance = context.get(controller_type)
                method_to_call = getattr(  # async event handler method lookup
                    controller_instance, method_name
                )  # 프레임워크 내부: 이벤트 핸들러 메서드 동적 디스패치
                return method_to_call(*args, **kwargs)

            consumer.register(route.event_type, endpoint)
            if hasattr(  # optional auth-aware Kafka consumer bridge
                consumer,
                "register_auth_boundary",
            ):
                consumer.register_auth_boundary(endpoint)
        return pod
