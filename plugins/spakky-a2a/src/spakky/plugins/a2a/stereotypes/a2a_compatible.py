"""@A2ACompatible marker for exposing an @Agent over the A2A protocol.

Unlike ``@GrpcController`` (which subclasses ``Controller`` and registers its own
Pod), this marker subclasses :class:`~spakky.core.pod.annotations.tag.Tag`: the
``@Agent`` decorator already registers the Pod, so this tag only records the A2A
transport metadata and stacks above ``@Agent`` on the same class.
"""

from dataclasses import dataclass

from spakky.core.pod.annotations.tag import Tag


@dataclass(eq=False)
class A2ACompatible(Tag):
    """Marks an @Agent class to be served through an A2A protocol endpoint.

    Attributes:
        base_url: Public transport endpoint advertised on the derived AgentCard.
        version: Semantic version advertised on the derived AgentCard.
        mount_path: Starlette/FastAPI mount path for automatic ASGI exposure.
    """

    base_url: str | None = None
    """Public endpoint advertised on the derived AgentCard interface."""

    version: str | None = None
    """Semantic version advertised on the derived AgentCard."""

    mount_path: str | None = None
    """ASGI host mount path. None uses ``A2AConfig.default_mount_path_prefix``."""

    rest_mount_path: str | None = None
    """Optional ASGI mount path for the HTTP+JSON REST transport."""

    rest_base_url: str | None = None
    """Public REST transport endpoint. None derives from default_base_url + path."""

    grpc_enabled: bool = False
    """Whether to register the official A2A gRPC handler when spakky-grpc is active."""

    grpc_base_url: str | None = None
    """Public gRPC transport endpoint advertised by the gRPC handler."""
