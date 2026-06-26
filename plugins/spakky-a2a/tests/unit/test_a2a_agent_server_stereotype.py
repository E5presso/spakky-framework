"""Tests for the @A2ACompatible marker."""

from spakky.agent.execution import Agent, AgentExecutionSpec
from spakky.agent.interfaces.model import IAgentModel
from spakky.core.pod.annotations.pod import Pod
import spakky.plugins.a2a as a2a_api
from spakky.plugins.a2a import A2ACompatible as PublicA2ACompatible

from spakky.plugins.a2a.stereotypes.a2a_compatible import A2ACompatible
from spakky.plugins.a2a.stereotypes.a2a_agent_server import A2AAgentServer


def test_marker_does_not_register_its_own_pod() -> None:
    """@A2ACompatible alone records metadata without registering a Pod."""

    @A2ACompatible(base_url="http://x", version="1.0.0")
    class PlainClass:
        pass

    assert not Pod.exists(PlainClass)
    assert A2ACompatible.exists(PlainClass)


def test_marker_stacks_above_agent_preserving_agent_pod() -> None:
    """Stacked above @Agent, the marker coexists with the agent's Pod."""

    @A2ACompatible(base_url="http://x", version="2.0.0")
    @Agent(spec=AgentExecutionSpec(name="stacked"))
    class StackedAgent:
        def __init__(self, model: IAgentModel) -> None:
            self._model = model

    assert Agent.exists(StackedAgent)
    assert A2ACompatible.exists(StackedAgent)


def test_marker_stores_base_url_and_version() -> None:
    """The marker preserves the declared base url and version."""

    @A2ACompatible(base_url="http://host:9000", version="3.1.4")
    class Marked:
        pass

    marker = A2ACompatible.get(Marked)
    assert marker.base_url == "http://host:9000"
    assert marker.version == "3.1.4"


def test_legacy_agent_server_name_aliases_compatible_marker() -> None:
    """The old @A2AAgentServer import remains a compatibility alias."""
    assert A2AAgentServer is A2ACompatible


def test_public_api_exports_compatible_marker() -> None:
    """The canonical public import exports @A2ACompatible."""
    assert PublicA2ACompatible is A2ACompatible
    assert a2a_api.A2ACompatible is A2ACompatible
