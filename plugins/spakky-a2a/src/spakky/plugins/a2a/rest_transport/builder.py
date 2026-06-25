"""Assembly helpers for the A2A HTTP+JSON REST transport."""

from a2a.server.routes import create_agent_card_routes, create_rest_routes
from a2a.utils import TransportProtocol
from spakky.agent.execution import Agent
from starlette.applications import Starlette

from spakky.plugins.a2a.card.derivation import AgentCardFactory
from spakky.plugins.a2a.server.request_handler import build_a2a_request_handler
from spakky.plugins.a2a.store.interfaces import IA2ATaskRepository


def build_a2a_rest_app(
    agent_instance: object,
    *,
    base_url: str,
    version: str,
    repository: IA2ATaskRepository | None = None,
    agent_type: type | None = None,
    path_prefix: str = "",
) -> Starlette:
    """Build a mountable A2A HTTP+JSON REST app for one @Agent instance.

    Args:
        agent_instance: The @Agent Pod instance to serve.
        base_url: Transport endpoint advertised on the derived AgentCard.
        version: Semantic version advertised on the derived AgentCard.
        repository: Task persistence port; an in-memory store is used when None.
        agent_type: Original @Agent class, supplied when the instance is proxied.
        path_prefix: Optional URL prefix for the REST operation routes.

    Returns:
        A Starlette application exposing AgentCard plus HTTP+JSON A2A routes.
    """
    card = AgentCardFactory().build(
        Agent.get(agent_type or type(agent_instance)),
        base_url,
        version,
        protocol=TransportProtocol.HTTP_JSON,
    )
    handler = build_a2a_request_handler(
        agent_instance,
        base_url=base_url,
        version=version,
        repository=repository,
        agent_type=agent_type,
        protocol=TransportProtocol.HTTP_JSON,
        card=card,
    )
    routes = [
        *create_agent_card_routes(card),
        *create_rest_routes(
            handler,
            enable_v0_3_compat=True,
            path_prefix=path_prefix,
        ),
    ]
    return Starlette(routes=routes)
