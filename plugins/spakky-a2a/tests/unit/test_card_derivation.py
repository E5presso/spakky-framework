"""Tests for AgentCard derivation from an @Agent declaration."""

import pytest
from spakky.agent.execution import (
    Agent,
    AgentExecutionSpec,
    AgentTeammate,
    StreamingExposureMode,
)
from spakky.agent.interfaces.model import IAgentModel
from spakky.agent.tooling import (
    DataAccess,
    Externality,
    Idempotency,
    ToolEffects,
    ToolPermission,
    agent_tool,
)

from spakky.plugins.a2a.card.derivation import (
    JSON_CONTENT_TYPE,
    TEXT_CONTENT_TYPE,
    AgentCardFactory,
)


@Agent(
    spec=AgentExecutionSpec(
        name="planner",
        objective="Plan a route across the city.",
        streaming_exposure_mode=StreamingExposureMode.BALANCED,
    )
)
class PlannerAgent:
    """Agent declaring one tool used to verify skill derivation."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model

    @agent_tool(
        schema_name="lookup_route",
        description="Look up a route.",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        permissions=(ToolPermission(name="maps:read"),),
    )
    def lookup_route(self, origin: str) -> str:
        """Return a route description for an origin."""
        return f"route from {origin}"


@Agent(spec=AgentExecutionSpec())
class AnonymousToollessAgent:
    """Agent with neither a name nor tools nor teammates."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model


def test_build_uses_spec_name_and_objective() -> None:
    """The card name and description come from the spec name and objective."""
    card = AgentCardFactory().build(Agent.get(PlannerAgent), "http://x", "1.0.0")

    assert card.name == "planner"
    assert card.description == "Plan a route across the city."
    assert card.version == "1.0.0"
    assert card.supported_interfaces[0].url == "http://x"


def test_build_falls_back_to_class_name_when_spec_name_absent() -> None:
    """The card name falls back to the class name when the spec omits a name."""
    card = AgentCardFactory().build(
        Agent.get(AnonymousToollessAgent), "http://x", "1.0.0"
    )

    assert card.name == "AnonymousToollessAgent"
    assert card.description == "AnonymousToollessAgent"


def test_build_disables_push_notifications() -> None:
    """The derived card never advertises push notifications."""
    card = AgentCardFactory().build(Agent.get(PlannerAgent), "http://x", "1.0.0")

    assert card.capabilities.push_notifications is False


@pytest.mark.parametrize(
    ("mode", "expected_streaming"),
    [
        (StreamingExposureMode.LOW_LATENCY, True),
        (StreamingExposureMode.BALANCED, True),
        (StreamingExposureMode.STRICT, True),
        (StreamingExposureMode.NO_STREAM_UNTIL_FINAL_GUARDED, False),
    ],
)
def test_build_streaming_capability_tracks_exposure_mode(
    mode: StreamingExposureMode,
    expected_streaming: bool,
) -> None:
    """Streaming capability is off only for the guarded final-only mode."""

    @Agent(
        spec=AgentExecutionSpec(
            name=f"probe_{mode.value}", streaming_exposure_mode=mode
        )
    )
    class StreamingProbeAgent:
        """Probe agent parametrized over each streaming exposure mode."""

        def __init__(self, model: IAgentModel) -> None:
            self._model = model

    card = AgentCardFactory().build(Agent.get(StreamingProbeAgent), "http://x", "1.0.0")

    assert card.capabilities.streaming is expected_streaming


def test_build_emits_one_skill_per_tool_descriptor() -> None:
    """Each tool descriptor projects to exactly one AgentSkill."""
    card = AgentCardFactory().build(Agent.get(PlannerAgent), "http://x", "1.0.0")

    descriptor = Agent.get(PlannerAgent).tool_catalog.descriptors[0]
    assert len(card.skills) == 1
    skill = card.skills[0]
    assert skill.id == descriptor.identity.key
    assert skill.name == descriptor.identity.name
    assert skill.description == "Look up a route."
    assert list(skill.input_modes) == [JSON_CONTENT_TYPE]
    assert list(skill.output_modes) == [JSON_CONTENT_TYPE]


def test_build_derives_skill_tags_from_tool_metadata() -> None:
    """Skill tags include permission names plus access, externality, idempotency."""
    card = AgentCardFactory().build(Agent.get(PlannerAgent), "http://x", "1.0.0")

    tags = list(card.skills[0].tags)
    assert tags == [
        "maps:read",
        DataAccess.READ.value,
        Externality.LOCAL.value,
        Idempotency.IDEMPOTENT.value,
    ]


def test_build_emits_one_skill_per_teammate() -> None:
    """Each declared teammate projects to a delegation AgentSkill."""

    @Agent(
        spec=AgentExecutionSpec(
            name="coordinator",
            teammates=(AgentTeammate(name="researcher", card_url="https://r.example"),),
        )
    )
    class CoordinatorAgent:
        """Agent declaring a remote teammate."""

        def __init__(self, model: IAgentModel) -> None:
            self._model = model

    card = AgentCardFactory().build(Agent.get(CoordinatorAgent), "http://x", "1.0.0")

    assert len(card.skills) == 1
    skill = card.skills[0]
    assert skill.id == "teammate:researcher"
    assert skill.name == "researcher"
    assert list(skill.tags) == ["delegation"]


def test_build_default_modes_are_text_plain() -> None:
    """Default input and output modes advertise plain text conversation."""
    card = AgentCardFactory().build(Agent.get(PlannerAgent), "http://x", "1.0.0")

    assert list(card.default_input_modes) == [TEXT_CONTENT_TYPE]
    assert list(card.default_output_modes) == [TEXT_CONTENT_TYPE]


def test_build_emits_no_skills_for_empty_catalog_and_no_teammates() -> None:
    """An agent with no tools and no teammates yields an empty skills list."""
    card = AgentCardFactory().build(
        Agent.get(AnonymousToollessAgent), "http://x", "1.0.0"
    )

    assert len(card.skills) == 0
