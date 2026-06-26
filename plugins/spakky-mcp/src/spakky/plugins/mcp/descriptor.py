"""Normalize external MCP servers into the agent tool catalog (issue #416).

ADR-0013 §2 keeps ``core/spakky-agent`` protocol-neutral and pushes the MCP
library dependency into this adapter plugin. Discovered MCP tools are kept in a
session-local registry and exposed to the model through two lazy meta-tools:
search the MCP toolset, then call one selected tool. This keeps large MCP
servers out of the initial model tool list while preserving the same dispatcher
path for the final invocation.
"""

import copy
import dataclasses
from collections.abc import Awaitable, Callable, Sequence
from inspect import isawaitable
from typing import cast, override

from mcp.types import CallToolResult, TextContent, Tool
from spakky.agent import (
    AgentRunner,
    AgentToolApprovalContext,
    AgentToolBoundInvocation,
    AgentToolCatalog,
    AgentToolDescriptor,
    AgentToolIdentity,
    AgentToolMetadata,
    AgentToolSchemaHandle,
    JsonObject,
    JsonValue,
    ToolApprovalRequirement,
    ToolEffects,
)
from spakky.agent.error import AgentDefinitionError

from spakky.plugins.mcp.constants import (
    MCP_EXTERNAL_TOOL_OWNER_MODULE,
    MCP_TOOL_NAME_SEPARATOR,
)
from spakky.plugins.mcp.error import (
    McpCatalogMergeError,
    McpResponseError,
    McpToolInvocationError,
)

# Callable bound to one external MCP tool. Its first parameter is VAR_KEYWORD,
# never self/cls, so the dispatcher invokes it without a bound target.
type McpToolCallable = Callable[..., Awaitable[JsonValue]]
# Builds a tool callable from a raw (unprefixed) MCP tool name; the live
# ``ClientSession`` is captured by the factory defined in ``client``.
type McpToolCallableFactory = Callable[[str], McpToolCallable]

MCP_SEARCH_TOOLS_NAME = "mcp_search_tools"
"""Model-facing lazy discovery tool for the current run's MCP toolset."""

MCP_CALL_TOOL_NAME = "mcp_call_tool"
"""Model-facing lazy invocation tool for a discovered MCP tool."""

DEFAULT_MCP_SEARCH_LIMIT = 20


class ExternalMcpTool:
    """Sentinel owner type for catalog descriptors discovered from MCP servers."""


class LazyMcpToolset:
    """Sentinel owner type for MCP lazy search/call descriptors."""


class ExternalMcpToolDescriptor(AgentToolDescriptor):
    """Descriptor that binds the MCP argument object verbatim to its callable.

    The core binder (``bind_agent_tool_invocation``) reserves top-level ``args``
    and ``kwargs`` payload keys for its positional/keyword structured-call form.
    An external MCP tool may legitimately declare input fields named ``args`` or
    ``kwargs``; routing such a payload through that heuristic would fail to bind
    or drop the field name. MCP tool inputs are always a flat JSON object, so
    this descriptor forwards the whole payload as keyword arguments without the
    structured-call interpretation, preserving every declared field name.
    """

    @override
    def bind_invocation(self, payload: JsonObject) -> AgentToolBoundInvocation:
        """Forward the MCP argument object as keyword arguments verbatim."""
        return AgentToolBoundInvocation(args=(), kwargs=dict(payload))


class LazyMcpCallToolDescriptor(AgentToolDescriptor):
    """Lazy call descriptor that surfaces the selected external tool to HITL."""

    @override
    def approval_context(self, payload: JsonObject) -> AgentToolApprovalContext:
        """Expose the target MCP tool name and arguments to approval requests."""
        tool_name = payload.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name.strip():
            return AgentToolApprovalContext()
        arguments = payload.get("arguments")
        safe_arguments = (
            cast(JsonObject, dict(arguments)) if isinstance(arguments, dict) else {}
        )
        return AgentToolApprovalContext(
            prompt=f"Approve MCP tool invocation: {tool_name.strip()}",
            action_ref=_external_tool_action_ref(tool_name.strip()),
            metadata={
                "mcp_meta_tool": MCP_CALL_TOOL_NAME,
                "mcp_tool_name": tool_name.strip(),
                "mcp_arguments": safe_arguments,
            },
        )


def prefixed_tool_name(server_name: str, raw_tool_name: str) -> str:
    """Return the collision-safe model-facing name for an external tool."""
    return f"{server_name}{MCP_TOOL_NAME_SEPARATOR}{raw_tool_name}"


def build_external_descriptor(
    server_name: str,
    tool: Tool,
    callable_: McpToolCallable,
) -> AgentToolDescriptor:
    """Normalize one discovered MCP tool into a catalog descriptor."""
    name = prefixed_tool_name(server_name, tool.name)
    identity = AgentToolIdentity(
        owner_module=MCP_EXTERNAL_TOOL_OWNER_MODULE,
        owner_qualname=f"{ExternalMcpTool.__qualname__}.{server_name}",
        name=name,
    )
    output_schema = cast(JsonObject, tool.outputSchema) if tool.outputSchema else {}
    schema = AgentToolSchemaHandle(
        name=name,
        input_schema_name=f"{name}.input",
        output_schema_name=f"{name}.output",
        input_schema=_normalize_input_schema(tool.inputSchema),
        output_schema=output_schema,
    )
    return ExternalMcpToolDescriptor(
        identity=identity,
        owner=ExternalMcpTool,
        callable=callable_,
        schema=schema,
        description=tool.description,
        metadata=_external_tool_metadata(),
    )


def build_external_descriptors(
    server_name: str,
    tools: Sequence[Tool],
    callable_factory: McpToolCallableFactory,
) -> tuple[AgentToolDescriptor, ...]:
    """Normalize all discovered tools of one server into catalog descriptors."""
    return tuple(
        build_external_descriptor(server_name, tool, callable_factory(tool.name))
        for tool in tools
    )


def merge_external_catalog(
    native: AgentToolCatalog,
    external: Sequence[AgentToolDescriptor],
) -> AgentToolCatalog:
    """Return a catalog combining native descriptors with external MCP tools."""
    try:
        return AgentToolCatalog(descriptors=(*native.descriptors, *external))
    except AgentDefinitionError as e:
        raise McpCatalogMergeError from e


def build_lazy_mcp_descriptors(
    external: Sequence[AgentToolDescriptor],
) -> tuple[AgentToolDescriptor, ...]:
    """Return the two model-visible tools that lazily expose MCP tools."""
    if not external:
        return ()
    by_name = {descriptor.schema.name: descriptor for descriptor in external}

    async def search_tools(
        query: str = "",
        limit: int = DEFAULT_MCP_SEARCH_LIMIT,
    ) -> JsonValue:
        """Search the MCP tools available to this run."""
        if limit <= 0:
            raise McpToolInvocationError("MCP search limit must be positive")
        matches = _filter_tool_summaries(external, query)
        return {
            "tools": matches[:limit],
            "count": min(len(matches), limit),
            "total": len(matches),
        }

    async def call_tool(tool_name: str, arguments: JsonObject) -> JsonValue:
        """Call one MCP tool by the name returned from mcp_search_tools."""
        if not tool_name.strip():
            raise McpToolInvocationError("MCP tool name cannot be blank")
        descriptor = by_name.get(tool_name)
        if descriptor is None:
            raise McpToolInvocationError("MCP tool name is not available")
        if not isinstance(arguments, dict):
            raise McpToolInvocationError("MCP tool arguments must be an object")
        bound = descriptor.bind_invocation(arguments)
        result = descriptor.callable(*bound.args, **bound.kwargs)
        if isawaitable(result):
            return cast(JsonValue, await result)
        return cast(JsonValue, result)

    return (
        _lazy_descriptor(
            name=MCP_SEARCH_TOOLS_NAME,
            callable_=search_tools,
            description=(
                "Search the MCP tools connected to this run. Use this before "
                "calling an MCP tool so the full external tool catalog does not "
                "need to be loaded into the initial model context."
            ),
            input_schema={
                "type": "object",
                "title": f"{MCP_SEARCH_TOOLS_NAME}.input",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Tool name, capability, or domain to search.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "default": DEFAULT_MCP_SEARCH_LIMIT,
                    },
                },
                "additionalProperties": False,
            },
            effects=ToolEffects.read_only(),
            approval=ToolApprovalRequirement.NOT_REQUIRED,
        ),
        _lazy_descriptor(
            name=MCP_CALL_TOOL_NAME,
            callable_=call_tool,
            description=(
                "Call one MCP tool returned by mcp_search_tools. Pass the "
                "tool_name exactly as returned and put the target tool payload "
                "inside arguments."
            ),
            input_schema={
                "type": "object",
                "title": f"{MCP_CALL_TOOL_NAME}.input",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "Exact MCP tool name returned by search.",
                    },
                    "arguments": {
                        "type": "object",
                        "description": "JSON object forwarded to the MCP tool.",
                        "additionalProperties": True,
                    },
                },
                "required": ["tool_name", "arguments"],
                "additionalProperties": False,
            },
            effects=ToolEffects.external_side_effect(),
            approval=ToolApprovalRequirement.DERIVED,
            descriptor_type=LazyMcpCallToolDescriptor,
        ),
    )


def build_mcp_runner(
    runner: AgentRunner,
    external: Sequence[AgentToolDescriptor],
) -> AgentRunner:
    """Build a runner whose catalog carries lazy MCP search/call tools.

    The caller supplies an already-open native runner so any request-scoped model
    resolver or durable-port assembly has already happened. The agent Pod
    metadata is a shared singleton, so its catalog is augmented on a ``copy.copy``.
    The actual external MCP descriptors stay hidden behind lazy meta-tools so a
    large MCP server does not flood the model request with every tool schema.
    """
    merged = merge_external_catalog(
        runner.agent.tool_catalog,
        build_lazy_mcp_descriptors(external),
    )
    augmented_agent = copy.copy(runner.agent)
    augmented_agent.tool_catalog = merged
    return dataclasses.replace(runner, agent=augmented_agent)


def normalize_call_result(result: CallToolResult) -> JsonValue:
    """Map an MCP tool result into a JSON value for evidence and the model."""
    if result.isError:
        raise McpToolInvocationError("MCP tool reported an error result")
    if result.structuredContent is not None:
        return cast(JsonValue, result.structuredContent)
    texts = [block.text for block in result.content if isinstance(block, TextContent)]
    if not texts:
        raise McpResponseError("MCP tool result carries no readable content")
    return {"content": texts}


def _normalize_input_schema(input_schema: object) -> JsonObject:
    if isinstance(input_schema, dict) and input_schema:
        return cast(JsonObject, input_schema)
    return {"type": "object", "properties": {}, "additionalProperties": True}


def _external_tool_metadata() -> AgentToolMetadata:
    effects = ToolEffects.external_side_effect()
    return AgentToolMetadata(
        effects=effects,
        data_access=effects.data_access,
        externality=effects.externality,
        approval=ToolApprovalRequirement.DERIVED,
    )


def _lazy_descriptor(
    *,
    name: str,
    callable_: Callable[..., Awaitable[JsonValue]],
    description: str,
    input_schema: JsonObject,
    effects: ToolEffects,
    approval: ToolApprovalRequirement,
    descriptor_type: type[AgentToolDescriptor] = AgentToolDescriptor,
) -> AgentToolDescriptor:
    identity = AgentToolIdentity(
        owner_module=MCP_EXTERNAL_TOOL_OWNER_MODULE,
        owner_qualname=LazyMcpToolset.__qualname__,
        name=name,
    )
    schema = AgentToolSchemaHandle(
        name=name,
        input_schema_name=f"{name}.input",
        output_schema_name=f"{name}.output",
        input_schema=input_schema,
        output_schema={"type": "object", "additionalProperties": True},
    )
    return descriptor_type(
        identity=identity,
        owner=LazyMcpToolset,
        callable=callable_,
        schema=schema,
        description=description,
        metadata=AgentToolMetadata(
            effects=effects,
            data_access=effects.data_access,
            externality=effects.externality,
            approval=approval,
        ),
    )


def _external_tool_action_ref(prefixed_name: str) -> str:
    server_name = prefixed_name.split(MCP_TOOL_NAME_SEPARATOR, 1)[0]
    return (
        f"{MCP_EXTERNAL_TOOL_OWNER_MODULE}."
        f"{ExternalMcpTool.__qualname__}.{server_name}:{prefixed_name}"
    )


def _filter_tool_summaries(
    descriptors: Sequence[AgentToolDescriptor],
    query: str,
) -> list[JsonObject]:
    normalized = query.strip().lower()
    summaries = [_tool_summary(descriptor) for descriptor in descriptors]
    if not normalized:
        return summaries
    return [
        summary
        for summary in summaries
        if normalized in _searchable_summary_text(summary)
    ]


def _tool_summary(descriptor: AgentToolDescriptor) -> JsonObject:
    return {
        "name": descriptor.schema.name,
        "description": descriptor.description,
        "input_schema": descriptor.schema.input_schema,
    }


def _searchable_summary_text(summary: JsonObject) -> str:
    values = [
        str(summary.get("name", "")),
        str(summary.get("description", "")),
        str(summary.get("input_schema", "")),
    ]
    return " ".join(values).lower()
