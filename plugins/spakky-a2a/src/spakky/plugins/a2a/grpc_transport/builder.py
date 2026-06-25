"""Assembly helpers for the A2A gRPC transport."""

from a2a.server.request_handlers import DefaultRequestHandler
from spakky.agent.execution import Agent

from spakky.plugins.a2a.card.derivation import AgentCardFactory
from spakky.plugins.a2a.executor.adapter import SpakkyAgentExecutor
from spakky.plugins.a2a.executor.event_mapping import AgentEventProjector
from spakky.plugins.a2a.grpc_transport.handler import A2AGrpcHandler
from spakky.plugins.a2a.store.interfaces import IA2ATaskRepository
from spakky.plugins.a2a.store.task_store import (
    InMemoryA2ATaskRepository,
    SpakkyA2ATaskStore,
)


def build_a2a_grpc_handler(
    agent_instance: object,
    *,
    base_url: str,
    version: str,
    repository: IA2ATaskRepository | None = None,
    agent_type: type | None = None,
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
    card = AgentCardFactory().build(
        Agent.get(agent_type or type(agent_instance)),
        base_url,
        version,
    )
    store = SpakkyA2ATaskStore(repository or InMemoryA2ATaskRepository())
    executor = SpakkyAgentExecutor(agent_instance, AgentEventProjector())
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=store,
        agent_card=card,
    )
    return A2AGrpcHandler(request_handler)
