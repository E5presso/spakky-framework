"""Sample @Agent declarations shared across A2A unit tests."""

from collections.abc import AsyncIterator
from typing import override

from spakky.agent.execution import Agent, AgentExecutionSpec
from spakky.agent.interfaces.model import (
    IAgentModel,
    ModelCapability,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
)
from spakky.agent.tooling import (
    Idempotency,
    ToolEffects,
    agent_tool,
)

from spakky.plugins.a2a.stereotypes.a2a_compatible import A2ACompatible


class StubModel(IAgentModel):
    """Minimal model double; never invoked by registry/builder tests."""

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        return
        yield  # pragma: no cover - empty async generator body


@A2ACompatible(base_url="http://planner.local", version="1.2.3")
@Agent(spec=AgentExecutionSpec(name="planner", objective="Plan things."))
class ServedPlannerAgent:
    """Agent marked for A2A serving, used by registry and builder tests."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model

    @agent_tool(
        schema_name="plan",
        description="Make a plan.",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
    )
    def plan(self, goal: str) -> str:
        """Return a plan for a goal."""
        return f"plan for {goal}"


@Agent(spec=AgentExecutionSpec(name="unserved"))
class UnservedAgent:
    """An @Agent without the A2A marker, used to verify it is skipped."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model
