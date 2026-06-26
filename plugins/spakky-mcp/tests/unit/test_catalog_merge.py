"""Unit tests for merging external MCP tools into the agent tool catalog."""

from collections.abc import AsyncGenerator, AsyncIterator
from typing import override

import pytest
from mcp.types import Tool
from spakky.agent import (
    Agent,
    AgentExecutionSpec,
    AgentRunner,
    AgentToolDescriptor,
    AgentYield,
    AgentYieldKind,
    Final,
    Idempotency,
    ModelCapability,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
)
from spakky.agent.interfaces.model import IAgentModel

from spakky.plugins.mcp.descriptor import (
    build_external_descriptor,
    build_mcp_runner,
    merge_external_catalog,
)
from spakky.plugins.mcp.error import McpCatalogMergeError


class _StubModel(IAgentModel):
    """Model port stub satisfying the runner's port resolution."""

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        raise NotImplementedError

    @override
    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        raise NotImplementedError


@Agent(spec=AgentExecutionSpec(name="weatherer", objective="report weather"))
class WeatherAgent:
    """Agent fixture exposing one native tool plus an injected model port."""

    def __init__(self, model: IAgentModel) -> None:
        self.model = model

    @agent_tool(
        schema_name="local.now",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def now(self) -> str:
        """Return a local timestamp label."""
        return "now"

    async def execute(
        self,
        command: str,
    ) -> AsyncGenerator[AgentYield[Final[str]], None]:
        """Satisfy the @Agent execute contract."""
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(output=command, metadata={}),
        )


async def _external_callable(**_arguments: object) -> str:
    return ""


def _external_descriptor(name: str = "get_data") -> AgentToolDescriptor:
    tool = Tool(
        name=name,
        description="external",
        inputSchema={"type": "object", "properties": {}},
    )
    return build_external_descriptor("weather", tool, _external_callable)


def test_merge_keeps_native_and_adds_external() -> None:
    """A merged catalog carries both native and external descriptors."""
    native = Agent.get(WeatherAgent).tool_catalog
    merged = merge_external_catalog(native, [_external_descriptor()])

    schema_names = {descriptor.schema.name for descriptor in merged.descriptors}
    assert "local.now" in schema_names
    assert "weather__get_data" in schema_names


def test_merge_rejects_schema_name_collision() -> None:
    """Two external tools resolving to the same prefixed name are rejected."""
    native = Agent.get(WeatherAgent).tool_catalog
    first = build_external_descriptor(
        "weather",
        Tool(name="get_data", description="x", inputSchema={"type": "object"}),
        _external_callable,
    )
    duplicate = build_external_descriptor(
        "weather",
        Tool(name="get_data", description="y", inputSchema={"type": "object"}),
        _external_callable,
    )

    with pytest.raises(McpCatalogMergeError):
        merge_external_catalog(native, [first, duplicate])


def test_build_mcp_runner_augments_catalog() -> None:
    """The runner sees a catalog combining native and external tools."""
    agent = WeatherAgent(_StubModel())
    runner = build_mcp_runner(
        AgentRunner.for_agent_instance(agent),
        [_external_descriptor()],
    )

    schema_names = {
        descriptor.schema.name for descriptor in runner.agent.tool_catalog.descriptors
    }
    assert schema_names == {"local.now", "weather__get_data"}


def test_build_mcp_runner_leaves_shared_agent_metadata_unmutated() -> None:
    """Augmenting the runner does not mutate the shared Agent Pod catalog."""
    agent = WeatherAgent(_StubModel())
    build_mcp_runner(AgentRunner.for_agent_instance(agent), [_external_descriptor()])

    shared_names = {
        descriptor.schema.name
        for descriptor in Agent.get(WeatherAgent).tool_catalog.descriptors
    }
    assert shared_names == {"local.now"}
