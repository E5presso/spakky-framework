"""Generic RPC handler for code-first gRPC service dispatch.

Routes incoming gRPC calls to ``@GrpcController`` methods by matching
the fully-qualified method name, performing protobuf ↔ dataclass
conversion transparently.
"""

import types
from collections.abc import AsyncIterator, Sequence
from dataclasses import fields, is_dataclass
from inspect import getmembers, isfunction
from logging import getLogger
from typing import Annotated, Callable, Union, get_args, get_origin

from google.protobuf.message import Message
from google.protobuf.message_factory import GetMessageClass
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.container import IContainer
from spakky.plugins.grpc.decorators.rpc import Rpc, RpcMethodType
from spakky.plugins.grpc.schema.registry import DescriptorRegistry

import grpc
import grpc.aio

logger = getLogger(__name__)


class GrpcServiceHandler(grpc.GenericRpcHandler):
    """Generic handler dispatching gRPC calls to ``@GrpcController`` methods.

    For each ``@rpc``-decorated method, builds a ``grpc.RpcMethodHandler``
    with serialiser/deserialiser that convert between protobuf wire format
    and Python dataclasses.

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
        """Create a ``grpc.RpcMethodHandler`` for a single ``@rpc`` method.

        Args:
            method_name: Controller method name.
            rpc_annotation: The ``@rpc`` annotation.
            request_deserializer: Bytes → domain object.
            response_serializer: Domain object → bytes.

        Returns:
            A configured ``grpc.RpcMethodHandler``.
        """
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
            self._application_context.clear_context()
            instance = self._container.get(self._controller_type)
            handler_method = getattr(instance, method_name)
            if request_type is None:
                return await handler_method()
            domain_request = (
                _protobuf_to_dataclass(request, request_type)
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
            self._application_context.clear_context()
            instance = self._container.get(self._controller_type)
            handler_method = getattr(instance, method_name)
            if request_type is None:
                async for item in handler_method():
                    yield item
                return
            domain_request = (
                _protobuf_to_dataclass(request, request_type)
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
            self._application_context.clear_context()
            instance = self._container.get(self._controller_type)
            handler_method = getattr(instance, method_name)

            async def _convert_stream() -> AsyncIterator[object]:
                async for request in request_iterator:
                    if request_type is not None and isinstance(request, Message):
                        yield _protobuf_to_dataclass(request, request_type)
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
            self._application_context.clear_context()
            instance = self._container.get(self._controller_type)
            handler_method = getattr(instance, method_name)

            async def _convert_stream() -> AsyncIterator[object]:
                async for request in request_iterator:
                    if request_type is not None and isinstance(request, Message):
                        yield _protobuf_to_dataclass(request, request_type)
                    else:
                        yield request

            async for item in handler_method(_convert_stream()):
                yield item

        return _behavior

    # ------ Serialisation helpers ------

    def _make_deserializer(
        self,
        request_type: type | None,
    ) -> Callable[[bytes], object] | None:
        """Build a bytes → protobuf Message deserializer.

        Args:
            request_type: The Python dataclass type for the request.

        Returns:
            A callable that parses raw bytes into a protobuf Message,
            or ``None`` when there is no request type.
        """
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
        response_type: type | None,
    ) -> Callable[[object], bytes] | None:
        """Build a domain object → bytes serializer.

        Args:
            response_type: The Python dataclass type for the response.

        Returns:
            A callable that serialises domain objects to protobuf bytes,
            or ``None`` when there is no response type.
        """
        if response_type is None:
            return None

        full_name = (
            f"{self._full_service_name.rsplit('.', 1)[0]}.{response_type.__name__}"
        )
        message_class = self._registry.get_message_class(full_name)

        def _serialize(obj: object) -> bytes:
            if isinstance(obj, Message):
                return obj.SerializeToString()
            msg = _dataclass_to_protobuf(obj, message_class)
            return msg.SerializeToString()

        return _serialize


# ------------------------------------------------------------------
# Module-level conversion helpers
# ------------------------------------------------------------------


def _is_optional(tp: object) -> bool:
    """Return ``True`` if *tp* is ``Optional[T]`` (i.e. ``T | None``)."""
    origin = get_origin(tp)
    if origin is Union or isinstance(tp, types.UnionType):
        return type(None) in get_args(tp)
    return False


def _protobuf_to_dataclass(message: Message, dataclass_type: type) -> object:
    """Convert a protobuf ``Message`` to a Python dataclass instance.

    Handles nested messages, repeated fields and optional (None) values.
    For proto3 optional fields, uses ``HasField`` to distinguish between
    an unset field (mapped to ``None``) and a field set to the default value.

    Args:
        message: The protobuf message.
        dataclass_type: The target dataclass type.

    Returns:
        An instance of *dataclass_type* populated from *message*.
    """
    kwargs: dict[str, object] = {}
    for field in fields(dataclass_type):
        resolved_type = _unwrap_annotated(field.type)
        if _is_optional(resolved_type) and message.HasField(field.name):
            raw = getattr(message, field.name)
            inner_type = next(a for a in get_args(resolved_type) if a is not type(None))
            kwargs[field.name] = _convert_proto_value(raw, inner_type)
        elif _is_optional(resolved_type):
            kwargs[field.name] = None
        else:
            raw = getattr(message, field.name)
            kwargs[field.name] = _convert_proto_value(raw, resolved_type)
    return dataclass_type(**kwargs)


def _unwrap_annotated(tp: object) -> object:
    """Unwrap ``Annotated[T, ...]`` to its inner type ``T``."""
    if get_origin(tp) is Annotated:
        return get_args(tp)[0]
    return tp


def _convert_proto_value(value: object, target_type: object) -> object:
    """Recursively convert a protobuf field value to its Python equivalent.

    Args:
        value: The raw protobuf field value.
        target_type: The expected Python type annotation.

    Returns:
        The converted value.
    """
    if isinstance(value, Message):
        if is_dataclass(target_type) and isinstance(target_type, type):
            return _protobuf_to_dataclass(value, target_type)
    origin = get_origin(target_type)
    if (
        origin is list
        and isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
    ):
        inner_args = get_args(target_type)
        if (
            inner_args
            and is_dataclass(inner_args[0])
            and isinstance(inner_args[0], type)
        ):
            return [
                _protobuf_to_dataclass(v, inner_args[0])
                if isinstance(v, Message)
                else v
                for v in value
            ]
        return list(value)
    return value


def _dataclass_to_protobuf(obj: object, message_class: type[Message]) -> Message:
    """Convert a Python dataclass to a protobuf ``Message``.

    Handles nested dataclasses and repeated fields.

    Args:
        obj: The dataclass instance.
        message_class: The target protobuf message class.

    Returns:
        A populated protobuf ``Message``.
    """
    msg = message_class()
    descriptor = msg.DESCRIPTOR
    for field_desc in descriptor.fields:
        value = getattr(obj, field_desc.name, None)
        if value is None:
            continue
        if (
            field_desc.label == field_desc.LABEL_REPEATED
            and field_desc.message_type is not None
            and isinstance(value, Sequence)
            and not isinstance(value, (str, bytes))
        ):
            nested_class = msg.DESCRIPTOR.fields_by_name[field_desc.name].message_type
            nested_msg_class = GetMessageClass(nested_class)
            for item in value:
                if is_dataclass(type(item)):
                    nested_msg = _dataclass_to_protobuf(item, nested_msg_class)
                    getattr(msg, field_desc.name).append(nested_msg)
                else:
                    getattr(msg, field_desc.name).append(item)
        elif field_desc.message_type is not None and is_dataclass(type(value)):
            nested_class = msg.DESCRIPTOR.fields_by_name[field_desc.name].message_type
            nested_msg_class = GetMessageClass(nested_class)
            nested_msg = _dataclass_to_protobuf(value, nested_msg_class)
            getattr(msg, field_desc.name).CopyFrom(nested_msg)
        elif field_desc.label == field_desc.LABEL_REPEATED:
            getattr(msg, field_desc.name).extend(value)  # type: ignore[arg-type] — protobuf repeated field .extend() accepts iterables
        else:
            setattr(msg, field_desc.name, value)
    return msg
