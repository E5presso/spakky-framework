"""Shared A2A request-handler assembly for all server transports."""

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.types import AgentCard
from a2a.utils import TransportProtocol
from spakky.agent.execution import Agent

from spakky.plugins.a2a.card.derivation import AgentCardFactory
from spakky.plugins.a2a.executor.adapter import SpakkyAgentExecutor
from spakky.plugins.a2a.executor.event_mapping import AgentEventProjector
from spakky.plugins.a2a.store.interfaces import IA2ATaskRepository
from spakky.plugins.a2a.store.task_store import (
    InMemoryA2ATaskRepository,
    SpakkyA2ATaskStore,
)


def build_a2a_request_handler(
    agent_instance: object,
    *,
    base_url: str,
    version: str,
    repository: IA2ATaskRepository | None = None,
    agent_type: type | None = None,
    protocol: TransportProtocol = TransportProtocol.JSONRPC,
    card: AgentCard | None = None,
) -> DefaultRequestHandler:
    """Build the official SDK request handler shared by A2A transports."""
    agent_card = card or AgentCardFactory().build(
        Agent.get(agent_type or type(agent_instance)),
        base_url,
        version,
        protocol=protocol,
    )
    store = SpakkyA2ATaskStore(repository or InMemoryA2ATaskRepository())
    executor = SpakkyAgentExecutor(agent_instance, AgentEventProjector())
    return DefaultRequestHandler(
        agent_executor=executor,
        task_store=store,
        agent_card=agent_card,
    )
