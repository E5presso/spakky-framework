"""Unit tests for merging external MCP tools into the agent tool catalog."""

from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from typing import cast, override

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
    JsonValue,
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
    MCP_CALL_TOOL_NAME,
    MCP_SEARCH_TOOLS_NAME,
    build_external_descriptor,
    build_lazy_mcp_descriptors,
    build_mcp_runner,
    merge_external_catalog,
)
from spakky.plugins.mcp.error import McpCatalogMergeError, McpToolInvocationError


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


async def _invoke_descriptor_callable(
    descriptor: AgentToolDescriptor,
    **arguments: object,
) -> JsonValue:
    callable_ = cast(Callable[..., Awaitable[JsonValue]], descriptor.callable)
    return await callable_(**arguments)


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
    """The runner sees native tools plus lazy MCP search/call tools."""
    agent = WeatherAgent(_StubModel())
    runner = build_mcp_runner(
        AgentRunner.for_agent_instance(agent),
        [_external_descriptor()],
    )

    schema_names = {
        descriptor.schema.name for descriptor in runner.agent.tool_catalog.descriptors
    }
    assert schema_names == {"local.now", MCP_SEARCH_TOOLS_NAME, MCP_CALL_TOOL_NAME}


def test_lazy_mcp_search_is_not_an_approval_candidate() -> None:
    """Searching tool metadata is local/read-only; calling remains external."""
    search, call = build_lazy_mcp_descriptors([_external_descriptor()])

    assert search.metadata.approval is ToolApprovalRequirement.NOT_REQUIRED
    assert search.metadata.requires_approval_candidate is False
    assert call.metadata.approval is ToolApprovalRequirement.DERIVED
    assert call.metadata.requires_approval_candidate is True


async def test_lazy_search_returns_matching_external_tool_summaries() -> None:
    """The search meta-tool returns MCP tool schemas without listing all upfront."""
    search, _call = build_lazy_mcp_descriptors(
        [
            _external_descriptor("get_weather"),
            _external_descriptor("search_docs"),
        ]
    )

    result = await _invoke_descriptor_callable(search, query="get_weather", limit=10)

    assert result == {
        "tools": [
            {
                "name": "weather__get_weather",
                "description": "external",
                "input_schema": {"type": "object", "properties": {}},
            }
        ],
        "count": 1,
        "total": 1,
    }


async def test_lazy_search_with_blank_query_returns_limited_summaries() -> None:
    """A blank search query lists the available MCP tool summaries up to limit."""
    search, _call = build_lazy_mcp_descriptors(
        [
            _external_descriptor("get_weather"),
            _external_descriptor("search_docs"),
        ]
    )

    result = await _invoke_descriptor_callable(search, query="", limit=1)

    assert result == {
        "tools": [
            {
                "name": "weather__get_weather",
                "description": "external",
                "input_schema": {"type": "object", "properties": {}},
            }
        ],
        "count": 1,
        "total": 2,
    }


async def test_lazy_call_invokes_selected_external_tool() -> None:
    """The call meta-tool forwards arguments to one selected MCP descriptor."""
    called: list[dict[str, object]] = []

    async def _callable(**arguments: object) -> JsonValue:
        called.append(dict(arguments))
        return {"ok": True}

    descriptor = build_external_descriptor(
        "weather",
        Tool(
            name="get_data",
            description="external",
            inputSchema={"type": "object", "properties": {}},
        ),
        _callable,
    )
    _search, call = build_lazy_mcp_descriptors([descriptor])

    result = await _invoke_descriptor_callable(
        call,
        tool_name="weather__get_data",
        arguments={"city": "seoul"},
    )

    assert result == {"ok": True}
    assert called == [{"city": "seoul"}]


async def test_lazy_search_rejects_non_positive_limit() -> None:
    """The search meta-tool rejects invalid result limits."""
    search, _call = build_lazy_mcp_descriptors([_external_descriptor()])

    with pytest.raises(McpToolInvocationError, match="search limit"):
        await _invoke_descriptor_callable(search, query="", limit=0)


async def test_lazy_call_rejects_blank_tool_name() -> None:
    """The call meta-tool requires a non-blank tool name."""
    _search, call = build_lazy_mcp_descriptors([_external_descriptor()])

    with pytest.raises(McpToolInvocationError, match="cannot be blank"):
        await _invoke_descriptor_callable(call, tool_name=" ", arguments={})


async def test_lazy_call_rejects_unknown_tool_name() -> None:
    """The call meta-tool only invokes tools returned by the search catalog."""
    _search, call = build_lazy_mcp_descriptors([_external_descriptor()])

    with pytest.raises(McpToolInvocationError, match="not available"):
        await _invoke_descriptor_callable(
            call, tool_name="weather__missing", arguments={}
        )


async def test_lazy_call_rejects_non_object_arguments() -> None:
    """The call meta-tool forwards only JSON object arguments to MCP tools."""
    _search, call = build_lazy_mcp_descriptors([_external_descriptor()])

    with pytest.raises(McpToolInvocationError, match="must be an object"):
        await _invoke_descriptor_callable(
            call,
            tool_name="weather__get_data",
            arguments=["not", "object"],
        )


async def test_lazy_call_accepts_sync_descriptor_callable_result() -> None:
    """The call meta-tool preserves compatibility with sync descriptor callables."""

    def _sync_callable(**arguments: object) -> JsonValue:
        return {"sync": cast(str, arguments["city"])}

    descriptor = build_external_descriptor(
        "weather",
        Tool(
            name="get_data",
            description="external",
            inputSchema={"type": "object", "properties": {}},
        ),
        cast(Callable[..., Awaitable[JsonValue]], _sync_callable),
    )
    _search, call = build_lazy_mcp_descriptors([descriptor])

    result = await _invoke_descriptor_callable(
        call,
        tool_name="weather__get_data",
        arguments={"city": "seoul"},
    )

    assert result == {"sync": "seoul"}


def test_build_mcp_runner_leaves_shared_agent_metadata_unmutated() -> None:
    """Augmenting the runner does not mutate the shared Agent Pod catalog."""
    agent = WeatherAgent(_StubModel())
    build_mcp_runner(AgentRunner.for_agent_instance(agent), [_external_descriptor()])

    shared_names = {
        descriptor.schema.name
        for descriptor in Agent.get(WeatherAgent).tool_catalog.descriptors
    }
    assert shared_names == {"local.now"}
