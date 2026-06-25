"""Tests for the @A2AAgentServer marker."""

from spakky.agent.execution import Agent, AgentExecutionSpec
from spakky.agent.interfaces.model import IAgentModel
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.a2a.stereotypes.a2a_agent_server import A2AAgentServer


def test_marker_does_not_register_its_own_pod() -> None:
    """@A2AAgentServer alone records metadata without registering a Pod."""

    @A2AAgentServer(base_url="http://x", version="1.0.0")
    class PlainClass:
        pass

    assert not Pod.exists(PlainClass)
    assert A2AAgentServer.exists(PlainClass)


def test_marker_stacks_above_agent_preserving_agent_pod() -> None:
    """Stacked above @Agent, the marker coexists with the agent's Pod."""

    @A2AAgentServer(base_url="http://x", version="2.0.0")
    @Agent(spec=AgentExecutionSpec(name="stacked"))
    class StackedAgent:
        def __init__(self, model: IAgentModel) -> None:
            self._model = model

    assert Agent.exists(StackedAgent)
    assert A2AAgentServer.exists(StackedAgent)


def test_marker_stores_base_url_and_version() -> None:
    """The marker preserves the declared base url and version."""

    @A2AAgentServer(base_url="http://host:9000", version="3.1.4")
    class Marked:
        pass

    marker = A2AAgentServer.get(Marked)
    assert marker.base_url == "http://host:9000"
    assert marker.version == "3.1.4"
