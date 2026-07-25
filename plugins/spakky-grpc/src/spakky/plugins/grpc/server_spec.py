"""Deferred gRPC server configuration.

``grpc.aio.server()`` binds to the current event loop at creation time, so
the real server must be instantiated on the event loop that eventually
runs it.  :class:`GrpcServerSpec` collects everything needed to build the
server (interceptors, generic handlers, bind targets, channel arguments,
standard-service registrations) during post-processing, and
:class:`GrpcServerService` materialises it at ``start_async`` time on the
correct loop.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

import grpc
import grpc.aio

type ServerServiceRegistrar = Callable[[grpc.aio.Server], Awaitable[None]]
"""Callback attaching a service to the server once it has been instantiated.

The standard health and reflection services ship as servicers that must be
registered on a concrete ``grpc.aio.Server``, which only exists after
:meth:`GrpcServerSpec.build_async`. Collecting them as callbacks keeps that
registration on the same deferred timeline as everything else in the spec.
They are awaitable because reporting an initial health status goes through the
servicer's async API on the serving loop.
"""


@dataclass(frozen=True)
class GrpcBindTarget:
    """One listener address together with the credentials protecting it.

    ``grpc.ServerCredentials`` is an opaque handle from the gRPC C core, so
    this pairing is a plain dataclass rather than a pydantic model.

    Attributes:
        address: Listener address in ``host:port`` form.
        credentials: TLS credentials, or ``None`` for a plaintext listener.
    """

    address: str
    credentials: grpc.ServerCredentials | None


class GrpcServerSpec:
    """Configuration collected during post-processing for deferred server creation.

    Attributes:
        handlers: Generic RPC handlers to register on the server.
        interceptors: Server interceptors to apply at creation time.
        bind_targets: Listener addresses with their transport credentials.
        service_registrars: Callbacks attaching standard services once the
            server object exists.
        options: Channel arguments passed to ``grpc.aio.server``.
        bound_ports: Ports returned when each bind target is attached,
            populated when :meth:`build_async` runs. Useful when binding to
            ``:0`` and needing to discover the OS-assigned port.
    """

    handlers: list[grpc.GenericRpcHandler]
    interceptors: list[grpc.aio.ServerInterceptor]
    bind_targets: list[GrpcBindTarget]
    service_registrars: list[ServerServiceRegistrar]
    options: tuple[tuple[str, int | str], ...]
    bound_ports: list[int]

    def __init__(self, options: Mapping[str, int | str] | None = None) -> None:
        """Initialise an empty spec.

        Args:
            options: Channel arguments for ``grpc.aio.server``. ``None`` keeps
                the gRPC defaults.
        """
        self.handlers = []
        self.interceptors = []
        self.bind_targets = []
        self.service_registrars = []
        self.options = tuple(options.items()) if options is not None else ()
        self.bound_ports = []

    @property
    def bind_addresses(self) -> list[str]:
        """Listener addresses in registration order."""
        return [target.address for target in self.bind_targets]

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

    def add_service_registrar(self, registrar: ServerServiceRegistrar) -> None:
        """Register a callback that attaches a service at build time.

        Args:
            registrar: Callback invoked with the instantiated server.
        """
        self.service_registrars.append(registrar)

    def add_insecure_port(self, address: str) -> None:
        """Register a plaintext bind address.

        Args:
            address: Address in ``host:port`` form.
        """
        self.bind_targets.append(GrpcBindTarget(address=address, credentials=None))

    def add_secure_port(
        self, address: str, credentials: grpc.ServerCredentials
    ) -> None:
        """Register a TLS-protected bind address.

        Args:
            address: Address in ``host:port`` form.
            credentials: Credentials terminating TLS on that address.
        """
        self.bind_targets.append(
            GrpcBindTarget(address=address, credentials=credentials)
        )

    async def build_async(self) -> grpc.aio.Server:
        """Instantiate the underlying ``grpc.aio.Server`` on the current loop.

        Must be awaited from the event loop that will run the server; see
        the module docstring for the rationale.

        Returns:
            The fully-configured server ready for ``.start()``.
        """
        server = grpc.aio.server(
            interceptors=list(self.interceptors),
            options=self.options,
        )
        server.add_generic_rpc_handlers(tuple(self.handlers))
        for register_service in self.service_registrars:
            await register_service(server)
        self.bound_ports = [self._bind(server, target) for target in self.bind_targets]
        return server

    @staticmethod
    def _bind(server: grpc.aio.Server, target: GrpcBindTarget) -> int:
        """Attach one bind target to *server* and return the resolved port."""
        if target.credentials is None:
            return server.add_insecure_port(target.address)
        return server.add_secure_port(target.address, target.credentials)
