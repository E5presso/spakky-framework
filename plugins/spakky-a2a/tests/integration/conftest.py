"""Integration fixtures driving the assembled A2A ASGI app in-process.

A scripted ``IAgentModel`` feeds the framework-owned ``AgentRunner`` so the full
message/send and message/stream lifecycle runs without any live LLM or network.
The served agent is durable (it accepts signals), so in-memory state, signal,
and evidence repositories are injected to satisfy the runner's durable path.
"""

from collections.abc import AsyncIterator, Iterator, Sequence
from typing import override

import httpx
import pytest
from a2a.utils import DEFAULT_RPC_URL
from spakky.agent.execution import (
    Agent,
    AgentExecutionSpec,
    AgentSignalKind,
    RecoveryStrategy,
)
from spakky.agent.interfaces.model import (
    IAgentModel,
    ModelCapability,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
)
from spakky.agent.tooling import (
    Idempotency,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
)
from starlette.applications import Starlette

from spakky.plugins.a2a.server.builder import build_a2a_app
from spakky.plugins.a2a.stereotypes.a2a_compatible import A2ACompatible
from tests.unit.conftest import (
    FakeEvidenceRepository,
    FakeSignalRepository,
    FakeStateRepository,
)

DURABLE_SPEC = AgentExecutionSpec(
    name="assistant",
    objective="Answer questions and gate writes on approval.",
    accepted_signals=(
        AgentSignalKind.USER_MESSAGE,
        AgentSignalKind.APPROVAL_DECISION,
        AgentSignalKind.CANCEL,
    ),
    recovery=RecoveryStrategy.ACTION_BOUNDARY,
)


class ScriptedModel(IAgentModel):
    """Model double replaying a fixed list of stream events per run."""

    def __init__(self, events: Sequence[ModelStreamEvent]) -> None:
        self._events = tuple(events)

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="scripted")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        for event in self._events:
            yield event


def _token(text: str) -> ModelStreamEvent:
    return ModelStreamEvent(kind=ModelStreamEventKind.TOKEN_DELTA, token_delta=text)


def _tool(name: str) -> ModelStreamEvent:
    return ModelStreamEvent(
        kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
        tool_call=ModelToolCall(name=name, arguments={"value": "x"}, call_id="c1"),
    )


@A2ACompatible(base_url="http://assistant.local", version="1.0.0")
@Agent(spec=DURABLE_SPEC)
class AssistantAgent:
    """Durable served agent exercised through the A2A transport."""

    def __init__(
        self,
        model: IAgentModel,
        states: FakeStateRepository,
        signals: FakeSignalRepository,
        evidence: FakeEvidenceRepository,
    ) -> None:
        self._model = model
        self._states = states
        self._signals = signals
        self._evidence = evidence

    @agent_tool(
        schema_name="write_note",
        description="Persist a note after approval.",
        effects=ToolEffects.write_state(),
        idempotency=Idempotency.CONDITIONALLY_IDEMPOTENT,
        approval=ToolApprovalRequirement.REQUIRED,
    )
    def write_note(self, value: str) -> str:
        """Write a note value and echo it back."""
        return f"wrote {value}"


def _build_agent(events: Sequence[ModelStreamEvent]) -> AssistantAgent:
    return AssistantAgent(
        ScriptedModel(events),
        FakeStateRepository(),
        FakeSignalRepository(),
        FakeEvidenceRepository(),
    )


def build_app(events: Sequence[ModelStreamEvent]) -> Starlette:
    """Assemble an A2A app over an assistant driven by scripted model events."""
    return build_a2a_app(
        _build_agent(events),
        base_url="http://assistant.local",
        version="1.0.0",
    )


@pytest.fixture
def rpc_url() -> str:
    """Expose the JSON-RPC mount path for request bodies."""
    return DEFAULT_RPC_URL


@pytest.fixture
def token_events() -> tuple[ModelStreamEvent, ...]:
    """A simple run streaming one token then terminating to a final output."""
    return (_token("hello "), _token("world"))


@pytest.fixture
def approval_events() -> tuple[ModelStreamEvent, ...]:
    """A run whose write tool requires approval, pausing for input."""
    return (_tool("write_note"),)


def make_client(app: Starlette) -> httpx.AsyncClient:
    """Open an httpx client bound to the in-process ASGI app."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


@pytest.fixture
def token_app(token_events: Sequence[ModelStreamEvent]) -> Iterator[Starlette]:
    """Provide an assembled app whose agent streams tokens to completion."""
    yield build_app(token_events)
