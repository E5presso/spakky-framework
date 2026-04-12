"""Deferred gRPC server configuration.

``grpc.aio.server()`` binds to the current event loop at creation time, so
the real server must be instantiated on the event loop that eventually
runs it.  :class:`GrpcServerSpec` collects everything needed to build the
server (interceptors, generic handlers, bind addresses) during
post-processing, and :class:`GrpcServerService` materialises it at
``start_async`` time on the correct loop.
"""

import grpc
import grpc.aio


class GrpcServerSpec:
    """Configuration collected during post-processing for deferred server creation.

    Attributes:
        handlers: Generic RPC handlers to register on the server.
        interceptors: Server interceptors to apply at creation time.
        bind_addresses: ``host:port`` strings to pass to ``add_insecure_port``.
    """

    handlers: list[grpc.GenericRpcHandler]
    interceptors: list[grpc.aio.ServerInterceptor]
    bind_addresses: list[str]

    def __init__(self) -> None:
        """Initialise an empty spec."""
        self.handlers = []
        self.interceptors = []
        self.bind_addresses = []

    def add_handler(self, handler: grpc.GenericRpcHandler) -> None:
        """Register a generic RPC handler.

        Args:
            handler: The handler to add to the server.
        """
        self.handlers.append(handler)

    def add_interceptor(self, interceptor: grpc.aio.ServerInterceptor) -> None:
        """Register a server interceptor.

        Args:
            interceptor: The interceptor to install on the server.
        """
        self.interceptors.append(interceptor)

    def add_insecure_port(self, address: str) -> None:
        """Register an insecure bind address.

        Args:
            address: Address in ``host:port`` form.
        """
        self.bind_addresses.append(address)

    def build(self) -> grpc.aio.Server:
        """Instantiate the underlying ``grpc.aio.Server`` on the current loop.

        Must be called from the event loop that will run the server; see
        the module docstring for the rationale.

        Returns:
            The fully-configured server ready for ``.start()``.
        """
        server = grpc.aio.server(interceptors=list(self.interceptors))
        server.add_generic_rpc_handlers(tuple(self.handlers))
        for address in self.bind_addresses:
            server.add_insecure_port(address)
        return server
