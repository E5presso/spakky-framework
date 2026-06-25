"""Tests for declarative agent tool dispatch."""

from collections.abc import AsyncGenerator

import pytest

from spakky.agent import (
    Agent,
    AgentExecutionSpec,
    AgentToolCatalog,
    AgentToolDescriptor,
    AgentToolDispatcher,
    AgentToolDispatchError,
    AgentToolIdentity,
    AgentToolSchemaHandle,
    AgentYield,
    AgentYieldKind,
    Final,
    Idempotency,
    ModelToolCall,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
)


@Agent(spec=AgentExecutionSpec(name="calculator", objective="run arithmetic tools"))
class CalculatorAgent:
    """Agent fixture exposing sync and async @agent_tool methods."""

    @agent_tool(
        schema_name="math.add",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def add(self, left: int, right: int) -> int:
        """Add two integers."""
        return left + right

    @agent_tool(
        schema_name="math.scale",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def scale(self, value: int, factor: int = 2) -> int:
        """Scale a value by an optional factor."""
        return value * factor

    @agent_tool(
        schema_name="math.fetch_remote_sum",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    async def fetch_remote_sum(self, numbers: list[int]) -> int:
        """Asynchronously sum a list of integers."""
        return sum(numbers)

    async def execute(
        self,
        command: str,
    ) -> AsyncGenerator[AgentYield[Final[str]], None]:
        """Satisfy the @Agent execute contract."""
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(output=command, metadata={}),
        )


def _calculator_dispatcher() -> AgentToolDispatcher:
    target = CalculatorAgent()
    return AgentToolDispatcher(
        target=target,
        catalog=Agent.get(CalculatorAgent).tool_catalog,
    )


async def test_dispatch_flat_payload_expect_sync_tool_invoked_with_bound_args() -> None:
    """flat keyword 페이로드가 sync 도구로 자동 바인딩·디스패치된다."""
    dispatcher = _calculator_dispatcher()

    result = await dispatcher.dispatch(
        ModelToolCall(name="math.add", arguments={"left": 3, "right": 4}),
    )

    assert result == 7


async def test_dispatch_omitted_argument_expect_descriptor_default_applied() -> None:
    """생략된 인자는 도구 signature default로 채워져 디스패치된다."""
    dispatcher = _calculator_dispatcher()

    result = await dispatcher.dispatch(
        ModelToolCall(name="math.scale", arguments={"value": 5}),
    )

    assert result == 10


async def test_dispatch_structured_payload_expect_args_kwargs_binding() -> None:
    """structured args/kwargs 페이로드가 positional·keyword로 바인딩된다."""
    dispatcher = _calculator_dispatcher()

    result = await dispatcher.dispatch(
        ModelToolCall(
            name="math.scale",
            arguments={"args": [5], "kwargs": {"factor": 3}},
        ),
    )

    assert result == 15


async def test_dispatch_async_tool_expect_awaited_result() -> None:
    """async 도구는 await되어 최종 결과를 반환한다."""
    dispatcher = _calculator_dispatcher()

    result = await dispatcher.dispatch(
        ModelToolCall(name="math.fetch_remote_sum", arguments={"numbers": [1, 2, 3]}),
    )

    assert result == 6


async def test_dispatch_unregistered_tool_expect_dispatch_error() -> None:
    """카탈로그에 없는 도구 호출은 커스텀 디스패치 에러로 실패한다."""
    dispatcher = _calculator_dispatcher()

    with pytest.raises(AgentToolDispatchError):
        await dispatcher.dispatch(
            ModelToolCall(name="math.unknown", arguments={"left": 1}),
        )


def test_descriptor_for_known_tool_expect_matching_descriptor() -> None:
    """모델 호출 이름으로 카탈로그 디스크립터를 조회한다."""
    dispatcher = _calculator_dispatcher()

    descriptor = dispatcher.descriptor_for(
        ModelToolCall(name="math.add", arguments={}),
    )

    assert descriptor.schema.name == "math.add"


async def test_dispatch_external_callable_expect_invoked_without_owner() -> None:
    """owner parameter가 없는 외부(MCP) 도구는 instance 없이 디스패치된다."""

    def remote_echo(message: str) -> str:
        return f"echo:{message}"

    descriptor = AgentToolDescriptor(
        identity=AgentToolIdentity(
            owner_module="mcp.remote",
            owner_qualname="RemoteToolset",
            name="remote.echo",
        ),
        owner=object,
        callable=remote_echo,
        schema=AgentToolSchemaHandle(
            name="remote.echo",
            input_schema_name="remote.echo.input",
            output_schema_name="remote.echo.output",
        ),
    )
    dispatcher = AgentToolDispatcher(
        target=object(),
        catalog=AgentToolCatalog(descriptors=(descriptor,)),
    )

    result = await dispatcher.dispatch(
        ModelToolCall(name="remote.echo", arguments={"message": "hi"}),
    )

    assert result == "echo:hi"
