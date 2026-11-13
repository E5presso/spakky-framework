"""Post-processor for registering API controller routes.

Automatically discovers and registers routes from @ApiController decorated
classes, creating FastAPI endpoints with proper dependency injection.
"""

from dataclasses import asdict
from functools import wraps
from inspect import (
    getmembers,
    isasyncgenfunction,
    isawaitable,
    isgeneratorfunction,
    signature,
)
from logging import getLogger
from collections.abc import Callable
from typing import Any, cast

from spakky.auth import AbstractSpakkyAuthError
from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from typing import override

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import FastAPIError
from fastapi.sse import EventSourceResponse
from fastapi.utils import (
    create_model_field,  # type: ignore[import-untyped] - fastapi.utils 내부 모듈, 타입 스텁 미제공
)
from spakky.plugins.fastapi.auth import (
    HTTP_AUTH_REQUEST_PARAMETER,
    WEBSOCKET_AUTH_PARAMETER,
    FastAPIAuthBoundary,
)
from spakky.plugins.fastapi.routes.route import Route
from spakky.plugins.fastapi.routes.websocket import WebSocketRoute
from spakky.plugins.fastapi.stereotypes.api_controller import ApiController

logger = getLogger(__name__)


async def _resolve_route_result(result: Any) -> Any:
    if isawaitable(result):
        return await result
    return result


@Order(0)
@Pod()
class RegisterRoutesPostProcessor(
    IPostProcessor, IContainerAware, IApplicationContextAware
):
    """Post-processor that registers routes from API controllers.

    Scans @ApiController decorated classes for @route decorated methods and
    automatically registers them as FastAPI endpoints with proper dependency
    injection and response model inference.
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
            application_context: The application context.
        """
        self.__application_context = application_context

    def __fastapi_apps(self) -> tuple[FastAPI, ...]:
        """Return all FastAPI application Pods currently registered."""
        return tuple(
            cast(FastAPI, fast_api)
            for fast_api in self.__application_context.find(
                lambda pod: pod.type_ is FastAPI or FastAPI in pod.base_types
            )
        )

    @override
    def post_process(self, pod: object) -> object:
        """Register routes from API controllers.

        Scans the controller for methods decorated with @route or @websocket
        and registers them as FastAPI endpoints. Automatically infers response
        models from return type annotations and sets up dependency injection.

        Args:
            pod: The Pod to process, potentially an API controller.

        Returns:
            The Pod, with routes registered if it's an API controller.
        """
        if not ApiController.exists(pod):
            return pod

        controller = ApiController.get(pod)
        router: APIRouter = APIRouter(prefix=controller.prefix, tags=controller.tags)
        for name, method in getmembers(pod, callable):
            route: Route | None = Route.get_or_none(method)
            websocket_route: WebSocketRoute | None = WebSocketRoute.get_or_none(method)
            if route is None and websocket_route is None:
                continue

            if route is not None:
                # pylint: disable=line-too-long
                logger.debug(
                    f"{route.methods!r} {controller.prefix}{route.path} -> {method.__qualname__}"
                )
                if route.name is None:
                    route.name = " ".join([x.capitalize() for x in name.split("_")])
                if route.description is None:
                    route.description = method.__doc__
                # The Pod may be an AOP proxy whose attributes hide the
                # generator nature, so the declaration on the class decides.
                declared_method = getattr(  # route decorator method lookup
                    controller.type_, name
                )  # 프레임워크 내부: 컨트롤러 메서드 선언 조회
                if issubclass(route.response_class, EventSourceResponse) and (
                    isasyncgenfunction(declared_method)
                    or isgeneratorfunction(declared_method)
                ):
                    self.__add_event_stream_route(
                        router, controller, name, method, declared_method, route
                    )
                    continue
                if route.response_model is None:
                    return_annotation: type | None = signature(method).return_annotation
                    if return_annotation is not None:
                        try:
                            create_model_field("", return_annotation)
                            route.response_model = return_annotation
                        except FastAPIError as e:
                            logger.debug(
                                f"Failed to infer response model for {method.__qualname__}: {type(e).__name__}"
                            )

                @wraps(method)
                async def endpoint(
                    *args: Any,
                    method_name: str = name,
                    controller_type: type[object] = controller.type_,
                    context: IContainer = self.__container,
                    **kwargs: Any,
                ) -> Any:
                    # Reset context so request-scoped Pods do not leak between
                    # consecutive FastAPI requests processed on the same worker.
                    self.__application_context.clear_context()
                    auth_request = kwargs.pop(HTTP_AUTH_REQUEST_PARAMETER)
                    controller_instance = context.get(controller_type)
                    method_to_call = getattr(  # route decorator method lookup
                        controller_instance, method_name
                    )  # 프레임워크 내부: 컨트롤러 메서드 동적 디스패치
                    auth_boundary = FastAPIAuthBoundary(
                        context,
                        self.__application_context,
                    )
                    try:
                        auth_boundary.seed_http_auth_context(
                            auth_request,
                            method_to_call,
                        )
                        for request_name in auth_boundary.request_argument_names(
                            method_to_call
                        ):
                            kwargs[request_name] = auth_request
                        return await _resolve_route_result(
                            method_to_call(*args, **kwargs)
                        )
                    except AbstractSpakkyAuthError as e:
                        auth_boundary.map_http_auth_error(e)

                auth_boundary = FastAPIAuthBoundary(
                    self.__container,
                    self.__application_context,
                )
                endpoint.__dict__["__signature__"] = (
                    auth_boundary.signature_with_request(method)
                )
                router.add_api_route(endpoint=endpoint, **asdict(route))
            if websocket_route is not None:
                # pylint: disable=line-too-long
                logger.debug(
                    f"[WebSocket] {controller.prefix}{websocket_route.path} -> {method.__qualname__}"
                )
                if websocket_route.name is None:
                    websocket_route.name = " ".join(
                        [x.capitalize() for x in name.split("_")]
                    )

                @wraps(method)
                async def websocket_endpoint(
                    *args: Any,
                    method_name: str = name,
                    controller_type: type[object] = controller.type_,
                    context: IContainer = self.__container,
                    **kwargs: Any,
                ) -> Any:
                    # WebSocket sessions reuse the same event loop task, so we
                    # clear the context to guarantee per-connection isolation.
                    self.__application_context.clear_context()
                    websocket = kwargs.pop(WEBSOCKET_AUTH_PARAMETER)
                    controller_instance = context.get(controller_type)
                    method_to_call = getattr(  # websocket decorator method lookup
                        controller_instance, method_name
                    )  # 프레임워크 내부: 컨트롤러 메서드 동적 디스패치
                    auth_boundary = FastAPIAuthBoundary(
                        context,
                        self.__application_context,
                    )
                    try:
                        auth_boundary.seed_websocket_auth_context(
                            websocket,
                            method_to_call,
                        )
                        for websocket_name in auth_boundary.websocket_argument_names(
                            method_to_call
                        ):
                            kwargs[websocket_name] = websocket
                        return await _resolve_route_result(
                            method_to_call(*args, **kwargs)
                        )
                    except AbstractSpakkyAuthError as e:
                        await auth_boundary.close_websocket_for_auth_error(websocket, e)
                        return None

                auth_boundary = FastAPIAuthBoundary(
                    self.__container,
                    self.__application_context,
                )
                websocket_endpoint.__dict__["__signature__"] = (
                    auth_boundary.signature_with_websocket(method)
                )
                router.add_api_websocket_route(
                    path=websocket_route.path,
                    endpoint=websocket_endpoint,
                    name=websocket_route.name,
                    dependencies=websocket_route.dependencies,
                )
        for fast_api in self.__fastapi_apps():
            fast_api.include_router(router)
        return pod

    def __add_event_stream_route(
        self,
        router: APIRouter,
        controller: ApiController,
        name: str,
        method: Callable[..., Any],  # Any: controller generator method signature
        declared_method: Callable[..., Any],  # Any: same method as declared on class
        route: Route,
    ) -> None:
        """Register a generator method as a native FastAPI SSE stream.

        FastAPI recognizes a generator endpoint through `functools.wraps`
        (`__wrapped__` is the generator function declared on the class) and calls it in the request handler before the response starts. The plain
        function below therefore resolves the controller and authenticates
        eagerly, so an auth failure is still an HTTP error response, and then
        hands the generator itself to FastAPI, which encodes the events, sends
        keep-alive comments and cancels the generator when the client leaves.

        Args:
            router: Router collecting the controller routes.
            controller: Controller stereotype of the Pod being processed.
            name: Attribute name of the generator method on the controller.
            method: The generator method found on the controller Pod.
            declared_method: The same method as declared on the controller class,
                which FastAPI inspects to recognize a generator endpoint.
            route: Route configuration whose response class is an SSE response.
        """

        @wraps(declared_method)
        def event_stream_endpoint(
            *args: Any,
            method_name: str = name,
            controller_type: type[object] = controller.type_,
            context: IContainer = self.__container,
            **kwargs: Any,
        ) -> Any:
            # Reset context so request-scoped Pods do not leak between
            # consecutive FastAPI requests processed on the same worker.
            self.__application_context.clear_context()
            auth_request = kwargs.pop(HTTP_AUTH_REQUEST_PARAMETER)
            controller_instance = context.get(controller_type)
            method_to_call = getattr(  # sse decorator method lookup
                controller_instance, method_name
            )  # 프레임워크 내부: 컨트롤러 메서드 동적 디스패치
            auth_boundary = FastAPIAuthBoundary(
                context,
                self.__application_context,
            )
            try:
                auth_boundary.seed_http_auth_context(
                    auth_request,
                    method_to_call,
                )
                for request_name in auth_boundary.request_argument_names(
                    method_to_call
                ):
                    kwargs[request_name] = auth_request
                return method_to_call(*args, **kwargs)
            except AbstractSpakkyAuthError as e:
                auth_boundary.map_http_auth_error(e)

        auth_boundary = FastAPIAuthBoundary(
            self.__container,
            self.__application_context,
        )
        event_stream_endpoint.__dict__["__signature__"] = (
            auth_boundary.signature_with_request(method)
        )
        route_options = asdict(route)
        if route.response_model is None:
            # Left unset so FastAPI infers the stream item type from the
            # generator's return annotation instead of disabling validation.
            del route_options["response_model"]
        router.add_api_route(endpoint=event_stream_endpoint, **route_options)
