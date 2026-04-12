"""Generic RPC handler for code-first gRPC service dispatch.

Routes incoming gRPC calls to ``@GrpcController`` methods by matching
the fully-qualified method name, performing protobuf ↔ pydantic
``BaseModel`` conversion via the ``google.protobuf.json_format``
bridge.
"""

from collections.abc import AsyncIterator
from inspect import getmembers, isfunction
from logging import getLogger
from typing import Callable, TypeVar

from google.protobuf import json_format
from google.protobuf.message import Message
from pydantic import BaseModel
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.container import IContainer
from typing_extensions import override

import grpc
import grpc.aio
from spakky.plugins.grpc.decorators.rpc import Rpc, RpcMethodType
from spakky.plugins.grpc.error import UnsupportedResponseTypeError
from spakky.plugins.grpc.schema.registry import DescriptorRegistry

logger = getLogger(__name__)

BaseModelT = TypeVar("BaseModelT", bound=BaseModel)


class GrpcServiceHandler(grpc.GenericRpcHandler):
    """Generic handler dispatching gRPC calls to ``@GrpcController`` methods.

    For each ``@rpc``-decorated method, builds a ``grpc.RpcMethodHandler``
    with serialiser/deserialiser that convert between protobuf wire
    format and pydantic ``BaseModel`` instances.

    Attributes:
        _full_service_name: Fully-qualified ``<package>.<service>`` name.
        _controller_type: The ``@GrpcController`` class.
        _container: IoC container for obtaining fresh controller instances.
        _application_context: Application context for request-scoped isolation.
        _registry: Descriptor registry for message class lookup.
        _handlers: Pre-built map of ``/<package>.<service>/<method>`` →
            ``RpcMethodHandler``.
    """

    _full_service_name: str
    _controller_type: type
    _container: IContainer
    _application_context: IApplicationContext
    _registry: DescriptorRegistry
    _handlers: dict[str, grpc.RpcMethodHandler]

    def __init__(
        self,
        *,
        controller_type: type,
        package: str,
        service_name: str,
        container: IContainer,
        application_context: IApplicationContext,
        registry: DescriptorRegistry,
    ) -> None:
        """Initialise the handler and pre-build per-method dispatchers.

        Args:
            controller_type: The ``@GrpcController``-decorated class.
            package: Protobuf package name.
            service_name: gRPC service name.
            container: IoC container for obtaining controller instances.
            application_context: Application context for request isolation.
            registry: Descriptor registry for message class lookup.
        """
        self._full_service_name = f"{package}.{service_name}"
        self._controller_type = controller_type
        self._container = container
        self._application_context = application_context
        self._registry = registry
        self._handlers = {}
        self._build_handlers()

    @override
    def service(
        self,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler | None:
        """Resolve an RPC method handler for the incoming call.

        Args:
            handler_call_details: Describes the incoming RPC.

        Returns:
            The matched handler, or ``None`` if not handled.
        """
        return self._handlers.get(handler_call_details.method)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_handlers(self) -> None:
        """Pre-build ``RpcMethodHandler`` for every ``@rpc`` method."""
        for method_name, method in getmembers(
            self._controller_type, predicate=isfunction
        ):
            rpc_annotation = Rpc.get_or_none(method)
            if rpc_annotation is None:
                continue

            full_method = f"/{self._full_service_name}/{method_name}"
            request_deserializer = self._make_deserializer(rpc_annotation.request_type)
            response_serializer = self._make_serializer(rpc_annotation.response_type)
            handler = self._make_rpc_method_handler(
                method_name=method_name,
                rpc_annotation=rpc_annotation,
                request_deserializer=request_deserializer,
                response_serializer=response_serializer,
            )
            self._handlers[full_method] = handler
            logger.debug(
                f"Registered gRPC method {full_method} "
                f"({rpc_annotation.method_type.value})"
            )

    def _make_rpc_method_handler(
        self,
        *,
        method_name: str,
        rpc_annotation: Rpc,
        request_deserializer: Callable[[bytes], object] | None,
        response_serializer: Callable[[object], bytes] | None,
    ) -> grpc.RpcMethodHandler:
        """Create a ``grpc.RpcMethodHandler`` for a single ``@rpc`` method."""
        method_type = rpc_annotation.method_type

        if method_type is RpcMethodType.UNARY:
            return grpc.unary_unary_rpc_method_handler(
                self._make_unary_behavior(method_name, rpc_annotation),
                request_deserializer=request_deserializer,
                response_serializer=response_serializer,
            )
        if method_type is RpcMethodType.SERVER_STREAMING:
            return grpc.unary_stream_rpc_method_handler(
                self._make_server_streaming_behavior(method_name, rpc_annotation),
                request_deserializer=request_deserializer,
                response_serializer=response_serializer,
            )
        if method_type is RpcMethodType.CLIENT_STREAMING:
            return grpc.stream_unary_rpc_method_handler(
                self._make_client_streaming_behavior(method_name, rpc_annotation),
                request_deserializer=request_deserializer,
                response_serializer=response_serializer,
            )
        # BIDI_STREAMING
        return grpc.stream_stream_rpc_method_handler(
            self._make_bidi_streaming_behavior(method_name, rpc_annotation),
            request_deserializer=request_deserializer,
            response_serializer=response_serializer,
        )

    # ------ Behaviour factories ------

    def _make_unary_behavior(
        self,
        method_name: str,
        rpc_annotation: Rpc,
    ) -> Callable[..., object]:
        """Build an async unary-unary handler."""
        request_type = rpc_annotation.request_type

        async def _behavior(
            request: object,
            context: grpc.aio.ServicerContext,
        ) -> object:
            del context
            self._application_context.clear_context()
            instance = self._container.get(self._controller_type)
            # framework 내부 디스패치: @rpc 등록 메서드명을 런타임에 조회
            handler_method = getattr(instance, method_name)
            if request_type is None:
                return await handler_method()
            domain_request = (
                _protobuf_to_basemodel(request, request_type)
                if isinstance(request, Message)
                else request
            )
            return await handler_method(domain_request)

        return _behavior

    def _make_server_streaming_behavior(
        self,
        method_name: str,
        rpc_annotation: Rpc,
    ) -> Callable[..., AsyncIterator[object]]:
        """Build an async unary-stream (server streaming) handler."""
        request_type = rpc_annotation.request_type

        async def _behavior(
            request: object,
            context: grpc.aio.ServicerContext,
        ) -> AsyncIterator[object]:
            del context
            self._application_context.clear_context()
            instance = self._container.get(self._controller_type)
            # framework 내부 디스패치: @rpc 등록 메서드명을 런타임에 조회
            handler_method = getattr(instance, method_name)
            if request_type is None:
                async for item in handler_method():
                    yield item
                return
            domain_request = (
                _protobuf_to_basemodel(request, request_type)
                if isinstance(request, Message)
                else request
            )
            async for item in handler_method(domain_request):
                yield item

        return _behavior

    def _make_client_streaming_behavior(
        self,
        method_name: str,
        rpc_annotation: Rpc,
    ) -> Callable[..., object]:
        """Build an async stream-unary (client streaming) handler."""
        request_type = rpc_annotation.request_type

        async def _behavior(
            request_iterator: AsyncIterator[object],
            context: grpc.aio.ServicerContext,
        ) -> object:
            del context
            self._application_context.clear_context()
            instance = self._container.get(self._controller_type)
            # framework 내부 디스패치: @rpc 등록 메서드명을 런타임에 조회
            handler_method = getattr(instance, method_name)

            async def _convert_stream() -> AsyncIterator[object]:
                async for request in request_iterator:
                    if request_type is not None and isinstance(request, Message):
                        yield _protobuf_to_basemodel(request, request_type)
                    else:
                        yield request

            return await handler_method(_convert_stream())

        return _behavior

    def _make_bidi_streaming_behavior(
        self,
        method_name: str,
        rpc_annotation: Rpc,
    ) -> Callable[..., AsyncIterator[object]]:
        """Build an async stream-stream (bidirectional streaming) handler."""
        request_type = rpc_annotation.request_type

        async def _behavior(
            request_iterator: AsyncIterator[object],
            context: grpc.aio.ServicerContext,
        ) -> AsyncIterator[object]:
            del context
            self._application_context.clear_context()
            instance = self._container.get(self._controller_type)
            # framework 내부 디스패치: @rpc 등록 메서드명을 런타임에 조회
            handler_method = getattr(instance, method_name)

            async def _convert_stream() -> AsyncIterator[object]:
                async for request in request_iterator:
                    if request_type is not None and isinstance(request, Message):
                        yield _protobuf_to_basemodel(request, request_type)
                    else:
                        yield request

            async for item in handler_method(_convert_stream()):
                yield item

        return _behavior

    # ------ Serialisation helpers ------

    def _make_deserializer(
        self,
        request_type: type[BaseModel] | None,
    ) -> Callable[[bytes], object] | None:
        """Build a bytes → protobuf Message deserializer."""
        if request_type is None:
            return None

        full_name = (
            f"{self._full_service_name.rsplit('.', 1)[0]}.{request_type.__name__}"
        )
        message_class = self._registry.get_message_class(full_name)

        def _deserialize(data: bytes) -> Message:
            msg = message_class()
            msg.ParseFromString(data)
            return msg

        return _deserialize

    def _make_serializer(
        self,
        response_type: type[BaseModel] | None,
    ) -> Callable[[object], bytes] | None:
        """Build a ``BaseModel``/``Message`` → bytes serializer."""
        if response_type is None:
            return None

        full_name = (
            f"{self._full_service_name.rsplit('.', 1)[0]}.{response_type.__name__}"
        )
        message_class = self._registry.get_message_class(full_name)

        def _serialize(obj: object) -> bytes:
            if isinstance(obj, Message):
                return obj.SerializeToString()
            if isinstance(obj, BaseModel):
                msg = _basemodel_to_protobuf(obj, message_class)
                return msg.SerializeToString()
            raise UnsupportedResponseTypeError(type(obj))

        return _serialize


# ------------------------------------------------------------------
# Module-level conversion helpers
# ------------------------------------------------------------------


def _basemodel_to_protobuf(obj: BaseModel, message_class: type[Message]) -> Message:
    """Convert a pydantic ``BaseModel`` instance into a protobuf ``Message``.

    Uses the ``google.protobuf.json_format`` bridge: the model is
    serialised to JSON via pydantic's v2 ``model_dump_json`` API and
    then parsed into a protobuf ``Message`` by
    ``json_format.Parse``. ``None`` values from optional fields are
    emitted as JSON ``null`` which ``json_format`` treats as "field
    unset" for proto3 optional fields.

    Args:
        obj: The pydantic ``BaseModel`` instance to convert.
        message_class: The target protobuf message class.

    Returns:
        A populated protobuf ``Message``.
    """
    payload = obj.model_dump_json()
    return json_format.Parse(
        payload,
        message_class(),
        ignore_unknown_fields=False,
    )


def _protobuf_to_basemodel(
    message: Message, model_type: type[BaseModelT]
) -> BaseModelT:
    """Convert a protobuf ``Message`` into a pydantic ``BaseModel`` instance.

    Uses the ``google.protobuf.json_format`` bridge: the message is
    serialised to JSON with ``preserving_proto_field_name=True`` so
    field names round-trip unchanged into ``model_validate_json``.

    Args:
        message: The protobuf message.
        model_type: The target ``BaseModel`` subclass.

    Returns:
        An instance of ``model_type`` populated from ``message``.
    """
    payload = json_format.MessageToJson(
        message,
        preserving_proto_field_name=True,
        always_print_fields_with_no_presence=True,
    )
    return model_type.model_validate_json(payload)
