"""Registers integration event handlers with the in-memory consumers."""

from functools import wraps
from logging import getLogger
from typing import Any, override

from spakky.auth import get_effective_auth_metadata
from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from spakky.domain.models.event import AbstractIntegrationEvent

from spakky.event.error import AbstractSpakkyEventError
from spakky.event.memory.consumer import (
    AsyncInMemoryEventConsumer,
    InMemoryEventConsumer,
)
from spakky.event.stereotype.event_handler import EventHandler

logger = getLogger(__name__)


class InMemoryProtectedHandlerUnsupportedError(AbstractSpakkyEventError):
    """Raised when an auth-protected handler is registered with the in-memory broker.

    The in-memory broker does not verify propagated auth snapshots. Running a
    protected handler without that check would silently bypass its requirement.
    """

    message = "In-memory event broker cannot enforce auth on protected handlers"
    handler: str

    def __init__(self, handler: str) -> None:
        self.handler = handler
        super().__init__()


@Order(1)
@Pod()
class InMemoryEventPostProcessor(
    IPostProcessor, IContainerAware, IApplicationContextAware
):
    """Scans `@EventHandler` Pods and registers their integration handlers."""

    __container: IContainer
    __application_context: IApplicationContext

    @override
    def set_container(self, container: IContainer) -> None:
        """Keep the container used to resolve handler instances per delivery."""
        self.__container = container

    @override
    def set_application_context(self, application_context: IApplicationContext) -> None:
        """Keep the context cleared before every delivery."""
        self.__application_context = application_context

    @override
    def post_process(self, pod: object) -> object:
        """Register every integration handler method of an event handler Pod.

        Raises:
            InMemoryProtectedHandlerUnsupportedError: A handler requires auth.
        """
        if not EventHandler.exists(pod):
            return pod
        handler: EventHandler = EventHandler.get(pod)
        consumer = self.__container.get(InMemoryEventConsumer)
        async_consumer = self.__container.get(AsyncInMemoryEventConsumer)
        for declared in handler.routes():
            route = declared.route
            name = declared.method_name
            if not issubclass(route.event_type, AbstractIntegrationEvent):
                continue
            handler_name = declared.handler_name
            method = getattr(  # declared handler function lookup
                handler.type_, name
            )  # 프레임워크 내부: 선언된 처리기 함수의 메타데이터 조회
            if get_effective_auth_metadata(method, owner_type=handler.type_).protected:
                raise InMemoryProtectedHandlerUnsupportedError(handler_name)
            logger.info(
                f"[{type(self).__name__}] {route.event_type.__name__} -> "
                f"{method.__qualname__} (subscriber {handler.subscriber!r})"
            )

            if declared.asynchronous:

                @wraps(method)
                async def async_endpoint(
                    *args: Any,
                    method_name: str = name,
                    controller_type: type[object] = handler.type_,
                    context: IContainer = self.__container,
                    **kwargs: Any,
                ) -> Any:
                    # 메시지마다 격리된 컨텍스트에서 처리기를 새로 해석한다.
                    self.__application_context.clear_context()
                    controller_instance = context.get(controller_type)
                    method_to_call = getattr(  # event handler method lookup
                        controller_instance, method_name
                    )  # 프레임워크 내부: 이벤트 핸들러 메서드 동적 디스패치
                    return await method_to_call(*args, **kwargs)

                async_consumer.register(
                    route.event_type,
                    async_endpoint,
                    subscriber=handler.subscriber,
                    handler_name=handler_name,
                )
                continue

            @wraps(method)
            def endpoint(
                *args: Any,
                method_name: str = name,
                controller_type: type[object] = handler.type_,
                context: IContainer = self.__container,
                **kwargs: Any,
            ) -> Any:
                # 메시지마다 격리된 컨텍스트에서 처리기를 새로 해석한다.
                self.__application_context.clear_context()
                controller_instance = context.get(controller_type)
                method_to_call = getattr(  # event handler method lookup
                    controller_instance, method_name
                )  # 프레임워크 내부: 이벤트 핸들러 메서드 동적 디스패치
                return method_to_call(*args, **kwargs)

            consumer.register(
                route.event_type,
                endpoint,
                subscriber=handler.subscriber,
                handler_name=handler_name,
            )
        return pod
