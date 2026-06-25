"""AgentCard derivation from an @Agent declaration.

Maps a spakky ``@Agent`` spec, its discovered tool catalog, and its declared
teammates onto an a2a-sdk ``AgentCard``. The a2a-sdk 1.x ``AgentCard`` is a
protobuf message (``a2a_pb2``) whose transport endpoint is expressed as an
``AgentInterface`` entry rather than a flat ``url`` field, so the base URL is
advertised through ``supported_interfaces``.
"""

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
)
from a2a.utils import TransportProtocol
from spakky.agent.execution import Agent, AgentTeammate, StreamingExposureMode
from spakky.agent.tooling import AgentToolDescriptor, AgentToolMetadata

JSON_CONTENT_TYPE = "application/json"
"""Tool skills advertise JSON-shaped input and output payloads."""

TEXT_CONTENT_TYPE = "text/plain"
"""The card's default conversational input and output content type."""

TEAMMATE_DELEGATION_TAG = "delegation"
"""Tag attached to a skill derived from a declared teammate."""


class AgentCardFactory:
    """Builds an a2a-sdk ``AgentCard`` from an @Agent Pod declaration."""

    def build(self, agent: Agent, base_url: str, version: str) -> AgentCard:
        """Derive an AgentCard from an @Agent spec, tools, and teammates.

        Args:
            agent: The @Agent Pod metadata carrying spec and tool catalog.
            base_url: Transport endpoint advertised on the card interface.
            version: Semantic version advertised on the card.

        Returns:
            A protobuf ``AgentCard`` ready to publish on the well-known route.
        """
        spec = agent.spec
        name = spec.name or agent.target.__name__
        description = spec.objective or spec.instructions or name
        # A guarded final-only profile suppresses incremental streaming exposure.
        streaming = (
            spec.streaming_exposure_mode
            is not StreamingExposureMode.NO_STREAM_UNTIL_FINAL_GUARDED
        )
        tool_skills = [
            self._tool_skill(descriptor)
            for descriptor in agent.tool_catalog.descriptors
        ]
        teammate_skills = [
            self._teammate_skill(teammate) for teammate in spec.teammates
        ]
        return AgentCard(
            name=name,
            description=description,
            version=version,
            supported_interfaces=[
                AgentInterface(
                    url=base_url,
                    protocol_binding=TransportProtocol.JSONRPC.value,
                )
            ],
            capabilities=AgentCapabilities(
                streaming=streaming,
                push_notifications=False,
            ),
            default_input_modes=[TEXT_CONTENT_TYPE],
            default_output_modes=[TEXT_CONTENT_TYPE],
            skills=[*tool_skills, *teammate_skills],
        )

    @staticmethod
    def _tool_skill(descriptor: AgentToolDescriptor) -> AgentSkill:
        """Project one tool descriptor onto an AgentSkill."""
        return AgentSkill(
            id=descriptor.identity.key,
            name=descriptor.identity.name,
            description=descriptor.description or descriptor.identity.name,
            tags=AgentCardFactory._skill_tags(descriptor.metadata),
            input_modes=[JSON_CONTENT_TYPE],
            output_modes=[JSON_CONTENT_TYPE],
        )

    @staticmethod
    def _teammate_skill(teammate: AgentTeammate) -> AgentSkill:
        """Project one declared teammate onto a delegation AgentSkill."""
        return AgentSkill(
            id=f"teammate:{teammate.name}",
            name=teammate.name,
            description="Delegated teammate",
            tags=[TEAMMATE_DELEGATION_TAG],
        )

    @staticmethod
    def _skill_tags(metadata: AgentToolMetadata) -> list[str]:
        """Derive deterministic skill tags from typed tool metadata."""
        return [
            *(permission.name for permission in metadata.permissions),
            metadata.data_access.value,
            metadata.externality.value,
            metadata.idempotency.value,
        ]
