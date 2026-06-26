"""Assembly helpers for the A2A gRPC transport."""

from a2a.utils import TransportProtocol
from spakky.agent.runner_factory import IAgentRunnerFactory

from spakky.plugins.a2a.grpc_transport.handler import A2AGrpcHandler
from spakky.plugins.a2a.server.request_handler import build_a2a_request_handler
from spakky.plugins.a2a.store.interfaces import IA2ATaskRepository


def build_a2a_grpc_handler(
    agent_instance: object,
    *,
    base_url: str,
    version: str,
    repository: IA2ATaskRepository | None = None,
    agent_type: type | None = None,
    runner_factory: IAgentRunnerFactory | None = None,
) -> A2AGrpcHandler:
    """Build a gRPC handler for one @Agent-backed A2A server.

    Args:
        agent_instance: The @Agent Pod instance to serve.
        base_url: Transport endpoint advertised on the derived AgentCard.
        version: Semantic version advertised on the derived AgentCard.
        repository: Task persistence port; an in-memory store is used when None.
        agent_type: Original @Agent class, supplied when the instance is proxied.

    Returns:
        A generic gRPC handler exposing the official A2A service methods.
    """
    request_handler = build_a2a_request_handler(
        agent_instance,
        base_url=base_url,
        version=version,
        repository=repository,
        agent_type=agent_type,
        protocol=TransportProtocol.GRPC,
        runner_factory=runner_factory,
    )
    return A2AGrpcHandler(request_handler)
