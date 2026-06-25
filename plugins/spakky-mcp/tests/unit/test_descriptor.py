"""Unit tests for normalizing MCP tools into agent catalog descriptors."""

import pytest
from mcp.types import CallToolResult, TextContent, Tool
from spakky.agent import (
    DataAccess,
    Externality,
    ToolApprovalRequirement,
    ToolRiskAxis,
)

from spakky.plugins.mcp.constants import MCP_EXTERNAL_TOOL_OWNER_MODULE
from spakky.plugins.mcp.descriptor import (
    ExternalMcpTool,
    build_external_descriptor,
    normalize_call_result,
    prefixed_tool_name,
)
from spakky.plugins.mcp.error import McpResponseError, McpToolInvocationError


async def _unused_callable(**_arguments: object) -> str:
    """Placeholder callable for descriptor-shape assertions."""
    return ""


def _tool(name: str = "echo", input_schema: dict[str, object] | None = None) -> Tool:
    return Tool(
        name=name,
        description="Echo a message",
        inputSchema=input_schema
        if input_schema is not None
        else {"type": "object", "properties": {"text": {"type": "string"}}},
    )


def test_prefixed_tool_name_joins_server_and_tool() -> None:
    """The model-facing name folds the server name in front of the tool name."""
    assert prefixed_tool_name("weather", "get_data") == "weather__get_data"


def test_descriptor_identity_is_server_scoped() -> None:
    """An external descriptor's identity is keyed by server and prefixed name."""
    descriptor = build_external_descriptor(
        "weather", _tool("get_data"), _unused_callable
    )

    assert descriptor.identity.owner_module == MCP_EXTERNAL_TOOL_OWNER_MODULE
    assert descriptor.identity.owner_qualname == "ExternalMcpTool.weather"
    assert descriptor.identity.name == "weather__get_data"
    assert descriptor.owner is ExternalMcpTool


def test_descriptor_passes_input_schema_through() -> None:
    """A non-empty MCP input schema is carried verbatim to the model surface."""
    schema: dict[str, object] = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
    }
    descriptor = build_external_descriptor(
        "weather", _tool(input_schema=schema), _unused_callable
    )

    assert descriptor.schema.name == "weather__echo"
    assert descriptor.schema.input_schema == schema


def test_descriptor_falls_back_for_empty_input_schema() -> None:
    """An empty MCP input schema becomes a permissive object schema."""
    descriptor = build_external_descriptor(
        "weather", _tool(input_schema={}), _unused_callable
    )

    assert descriptor.schema.input_schema == {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }


def test_descriptor_carries_output_schema_when_present() -> None:
    """A declared MCP output schema is carried onto the descriptor."""
    tool = Tool(
        name="echo",
        description="Echo",
        inputSchema={"type": "object"},
        outputSchema={"type": "object", "properties": {"result": {"type": "string"}}},
    )
    descriptor = build_external_descriptor("weather", tool, _unused_callable)

    assert descriptor.schema.output_schema == {
        "type": "object",
        "properties": {"result": {"type": "string"}},
    }


def test_descriptor_metadata_marks_external_network_side_effect() -> None:
    """External tools derive a network side-effect risk and approval candidacy."""
    descriptor = build_external_descriptor("weather", _tool(), _unused_callable)
    metadata = descriptor.metadata

    assert metadata.data_access is DataAccess.READ_WRITE
    assert metadata.externality is Externality.EXTERNAL
    assert metadata.approval is ToolApprovalRequirement.DERIVED
    assert metadata.risk.includes(ToolRiskAxis.NETWORK)
    assert metadata.requires_approval_candidate is True


def test_normalize_call_result_prefers_structured_content() -> None:
    """A structured tool result is returned as the JSON object verbatim."""
    result = CallToolResult(
        content=[TextContent(type="text", text="ignored")],
        structuredContent={"result": 3},
    )

    assert normalize_call_result(result) == {"result": 3}


def test_normalize_call_result_joins_text_content() -> None:
    """Unstructured text content is collected under a content key."""
    result = CallToolResult(
        content=[
            TextContent(type="text", text="first"),
            TextContent(type="text", text="second"),
        ],
    )

    assert normalize_call_result(result) == {"content": ["first", "second"]}


def test_normalize_call_result_rejects_error_result() -> None:
    """A tool result flagged as an error surfaces an invocation error."""
    result = CallToolResult(
        content=[TextContent(type="text", text="boom")],
        isError=True,
    )

    with pytest.raises(McpToolInvocationError):
        normalize_call_result(result)


def test_normalize_call_result_rejects_empty_content() -> None:
    """A result with neither structured nor text content cannot be mapped."""
    result = CallToolResult(content=[])

    with pytest.raises(McpResponseError):
        normalize_call_result(result)


def test_external_descriptor_binds_payload_as_keyword_arguments() -> None:
    """The MCP argument object binds verbatim as keyword arguments."""
    descriptor = build_external_descriptor("weather", _tool(), _unused_callable)
    bound = descriptor.bind_invocation({"text": "hello"})

    assert bound.kwargs == {"text": "hello"}
    assert bound.args == ()


def test_external_descriptor_preserves_reserved_args_field() -> None:
    """A tool field named ``args`` survives instead of hitting the call heuristic.

    The core binder reserves a top-level ``args`` key for positional structured
    calls, which would fail to bind to the owner-less callable; the external
    descriptor forwards it verbatim so the MCP field name is preserved.
    """
    descriptor = build_external_descriptor("weather", _tool(), _unused_callable)
    bound = descriptor.bind_invocation({"args": ["a", "b"]})

    assert bound.kwargs == {"args": ["a", "b"]}
    assert bound.args == ()


def test_external_descriptor_preserves_reserved_kwargs_field() -> None:
    """A tool field named ``kwargs`` keeps its field name instead of unwrapping."""
    descriptor = build_external_descriptor("weather", _tool(), _unused_callable)
    bound = descriptor.bind_invocation({"kwargs": {"query": "rain"}})

    assert bound.kwargs == {"kwargs": {"query": "rain"}}
    assert bound.args == ()
