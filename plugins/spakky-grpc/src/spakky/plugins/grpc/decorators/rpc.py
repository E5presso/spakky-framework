"""RPC method decorator for gRPC service methods.

Provides the @rpc decorator for marking controller methods as gRPC service
methods with support for all four gRPC streaming patterns.
"""

from collections.abc import AsyncIterator as AsyncIteratorABC
from dataclasses import dataclass
from enum import StrEnum, auto
from inspect import signature
from typing import get_args, get_origin, get_type_hints
from collections.abc import Callable

from spakky.core.common.annotation import FunctionAnnotation


class RpcMethodType(StrEnum):
    """gRPC method streaming patterns.

    Attributes:
        UNARY: Single request, single response.
        SERVER_STREAMING: Single request, stream of responses.
        CLIENT_STREAMING: Stream of requests, single response.
        BIDI_STREAMING: Stream of requests, stream of responses.
    """

    UNARY = auto()
    SERVER_STREAMING = auto()
    CLIENT_STREAMING = auto()
    BIDI_STREAMING = auto()


def _unwrap_streaming_type(annotation: object | None) -> type | None:
    """Return the message type inside supported streaming annotations."""
    if annotation is AsyncIteratorABC:
        return None
    candidate = annotation
    if get_origin(annotation) is AsyncIteratorABC and get_args(annotation):
        args = get_args(annotation)
        candidate = args[0]
    if isinstance(candidate, type):
        return candidate
    return None


@dataclass
class Rpc(FunctionAnnotation):
    """Function annotation for marking methods as gRPC RPC endpoints.

    Stores RPC configuration including the streaming pattern and
    request/response type metadata.

    Attributes:
        method_type: gRPC streaming pattern for this method.
        request_type: Request message type. Auto-extracted from type hints
            if not provided.
        response_type: Response message type. Auto-extracted from type hints
            if not provided.
    """

    method_type: RpcMethodType = RpcMethodType.UNARY
    request_type: type | None = None
    response_type: type | None = None

    def __call__[T](self, obj: Callable[..., T]) -> Callable[..., T]:
        """Annotate a method as an RPC endpoint.

        Extracts request and response types from type hints if not
        explicitly provided.

        Args:
            obj: The method to annotate.

        Returns:
            The annotated method.
        """
        if self.request_type is None or self.response_type is None:
            self._extract_types(obj)
        return super().__call__(obj)

    def _extract_types(self, obj: Callable[..., object]) -> None:
        """Extract request/response types from function type hints.

        Args:
            obj: The function to extract types from.
        """
        hints = get_type_hints(obj)
        if self.request_type is None:
            params = list(signature(obj).parameters.values())
            non_self_params = [p for p in params if p.name != "self"]
            if non_self_params:
                request_hint = hints.get(non_self_params[0].name)
                self.request_type = _unwrap_streaming_type(request_hint)
        if self.response_type is None:
            response_hint = hints.get("return")
            self.response_type = _unwrap_streaming_type(response_hint)


def rpc[T](
    method_type: RpcMethodType = RpcMethodType.UNARY,
    request_type: type | None = None,
    response_type: type | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to mark a controller method as a gRPC RPC endpoint.

    Attaches RPC configuration to the method including streaming pattern
    and message type metadata.

    Args:
        method_type: gRPC streaming pattern for this method.
        request_type: Request message type. Auto-extracted from type hints
            if not provided.
        response_type: Response message type. Auto-extracted from type hints
            if not provided.

    Returns:
        A decorator function that attaches the RPC configuration.
    """

    def wrapper(method: Callable[..., T]) -> Callable[..., T]:
        return Rpc(
            method_type=method_type,
            request_type=request_type,
            response_type=response_type,
        )(method)

    return wrapper
