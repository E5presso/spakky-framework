"""Typed caller for a code-first ``@GrpcController`` service.

Without this, a caller has to rebuild the protobuf descriptor from its own
copy of the pydantic models. Because field numbers are derived from field
names, a single renamed field on either side moves that field's wire number
and the value silently disappears from the decoded message.

:class:`GrpcClient` removes the second copy: it takes the controller class
itself — the same declaration the server registers — builds the descriptor
from it, and derives every callable's serialiser from that descriptor. The
RPC method is identified by referencing the controller method rather than
by spelling its name in a string, so a renamed method breaks at import time
instead of at call time.
"""

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import cast

import grpc.aio
from pydantic import BaseModel

from spakky.plugins.grpc.codec import deserializer_for, serializer_for
from spakky.plugins.grpc.decorators.rpc import Rpc, RpcMethodType
from spakky.plugins.grpc.error import (
    MessagelessRpcMethodError,
    NotAnRpcMethodError,
    RpcMethodTypeMismatchError,
)
from spakky.plugins.grpc.schema.descriptor_builder import build_file_descriptor
from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController


class GrpcClient:
    """Builds gRPC callables for one ``@GrpcController`` service.

    The multicallable return types are written as strings because the gRPC
    runtime classes are only generic in the type stubs — subscripting them at
    class-definition time raises ``TypeError``.

    Attributes:
        registry: Registry holding the descriptor built from the controller.
    """

    registry: DescriptorRegistry

    _channel: grpc.aio.Channel
    _package: str
    _full_service_name: str

    def __init__(
        self,
        channel: grpc.aio.Channel,
        controller_type: type,
        registry: DescriptorRegistry | None = None,
    ) -> None:
        """Register the controller's descriptor and bind the client to a channel.

        Args:
            channel: Open channel to the server hosting the service.
            controller_type: The ``@GrpcController``-decorated class declaring
                the service.
            registry: Registry to compile the descriptor into. ``None`` creates
                a private one; pass the server's registry when calling a
                service that runs in the same process.
        """
        annotation = GrpcController.get(controller_type)
        self._channel = channel
        self._package = annotation.package
        self._full_service_name = (
            f"{annotation.package}."
            f"{annotation.service_name or controller_type.__name__}"
        )
        self.registry = registry if registry is not None else DescriptorRegistry()

        file_descriptor = build_file_descriptor(controller_type)
        if not self.registry.is_registered(file_descriptor.name):
            self.registry.register(file_descriptor)

    def unary_unary[SelfT, RequestT: BaseModel, ResponseT: BaseModel](
        self,
        method: Callable[[SelfT, RequestT], Coroutine[object, object, ResponseT]],
    ) -> "grpc.aio.UnaryUnaryMultiCallable[RequestT, ResponseT]":
        """Build a callable for a single-request, single-response method.

        Args:
            method: The ``@rpc`` method on the controller class, referenced
                unbound (``EchoController.unary_echo``).

        Returns:
            A multicallable accepting the request model and awaiting the
            response model.
        """
        method_path, serialize, deserialize = self._multicallable_arguments(
            method, RpcMethodType.UNARY
        )
        return self._channel.unary_unary(
            method_path,
            request_serializer=serialize,
            response_deserializer=deserialize,
        )

    def unary_stream[SelfT, RequestT: BaseModel, ResponseT: BaseModel](
        self,
        method: Callable[[SelfT, RequestT], AsyncIterator[ResponseT]],
    ) -> "grpc.aio.UnaryStreamMultiCallable[RequestT, ResponseT]":
        """Build a callable for a server-streaming method.

        Args:
            method: The ``@rpc`` method on the controller class, referenced
                unbound.

        Returns:
            A multicallable accepting the request model and yielding response
            models.
        """
        method_path, serialize, deserialize = self._multicallable_arguments(
            method, RpcMethodType.SERVER_STREAMING
        )
        return self._channel.unary_stream(
            method_path,
            request_serializer=serialize,
            response_deserializer=deserialize,
        )

    def stream_unary[SelfT, RequestT: BaseModel, ResponseT: BaseModel](
        self,
        method: Callable[
            [SelfT, AsyncIterator[RequestT]], Coroutine[object, object, ResponseT]
        ],
    ) -> "grpc.aio.StreamUnaryMultiCallable[RequestT, ResponseT]":
        """Build a callable for a client-streaming method.

        Args:
            method: The ``@rpc`` method on the controller class, referenced
                unbound.

        Returns:
            A multicallable accepting an async iterator of request models and
            awaiting the response model.
        """
        method_path, serialize, deserialize = self._multicallable_arguments(
            method, RpcMethodType.CLIENT_STREAMING
        )
        return self._channel.stream_unary(
            method_path,
            request_serializer=serialize,
            response_deserializer=deserialize,
        )

    def stream_stream[SelfT, RequestT: BaseModel, ResponseT: BaseModel](
        self,
        method: Callable[[SelfT, AsyncIterator[RequestT]], AsyncIterator[ResponseT]],
    ) -> "grpc.aio.StreamStreamMultiCallable[RequestT, ResponseT]":
        """Build a callable for a bidirectional-streaming method.

        Args:
            method: The ``@rpc`` method on the controller class, referenced
                unbound.

        Returns:
            A multicallable accepting an async iterator of request models and
            yielding response models.
        """
        method_path, serialize, deserialize = self._multicallable_arguments(
            method, RpcMethodType.BIDI_STREAMING
        )
        return self._channel.stream_stream(
            method_path,
            request_serializer=serialize,
            response_deserializer=deserialize,
        )

    def _multicallable_arguments[RequestT: BaseModel, ResponseT: BaseModel](
        self, method: Callable[..., object], expected: RpcMethodType
    ) -> tuple[str, Callable[[RequestT], bytes], Callable[[bytes], ResponseT]]:
        """Resolve the method path and codecs backing one multicallable.

        Args:
            method: The controller method being wrapped.
            expected: The streaming pattern the requested callable serves.

        Returns:
            The ``/<package>.<service>/<method>`` path, the request serialiser
            and the response deserialiser.

        Raises:
            NotAnRpcMethodError: If the method carries no ``@rpc`` annotation.
            RpcMethodTypeMismatchError: If the method's streaming pattern is
                not *expected*.
            MessagelessRpcMethodError: If the method declares no request or no
                response model.
        """
        rpc_annotation = Rpc.get_or_none(method)
        if rpc_annotation is None:
            raise NotAnRpcMethodError(method.__name__)
        if rpc_annotation.method_type is not expected:
            raise RpcMethodTypeMismatchError(
                method.__name__, expected, rpc_annotation.method_type
            )
        if rpc_annotation.request_type is None or rpc_annotation.response_type is None:
            raise MessagelessRpcMethodError(method.__name__)
        # `Rpc` stores both models as bare `type` objects erased of their identity,
        # while `RequestT`/`ResponseT` come from the controller method signature the
        # caller passed in — the same classes by construction of the `@rpc` decorator.
        return (
            f"/{self._full_service_name}/{method.__name__}",
            cast(
                Callable[[RequestT], bytes],
                serializer_for(
                    self.registry,
                    f"{self._package}.{rpc_annotation.request_type.__name__}",
                ),
            ),
            cast(
                Callable[[bytes], ResponseT],
                deserializer_for(
                    self.registry,
                    f"{self._package}.{rpc_annotation.response_type.__name__}",
                    rpc_annotation.response_type,
                ),
            ),
        )
