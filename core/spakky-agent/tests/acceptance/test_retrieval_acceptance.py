"""Acceptance coverage for classic and agentic retrieval through AgentRunner."""

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import replace
from typing import cast, override

import pytest
from pydantic import BaseModel

from spakky.agent import (
    Agent,
    AgentDefinitionError,
    AgentEvidenceKind,
    AgentExecutionSpec,
    AgentRunner,
    AgentStateReason,
    AgentStatus,
    AgentToolCatalog,
    AgentYieldKind,
    Error,
    Final,
    IAgentModel,
    IAgentToolProvider,
    IRetriever,
    JsonObject,
    ModelCapability,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    RecoveryStrategy,
    RetrievalContext,
    RetrievalHit,
    RetrievalTool,
    RunFinishedEvent,
    RunAgentInput,
    Tool,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
    discover_agent_tools,
)
from tests.unit.test_code_assistant_demo import (
    FakeEvidenceRepository,
    FakeSignalRepository,
    FakeStateRepository,
)


class Answer(BaseModel):
    answer: str


class AcceptanceRetriever(IRetriever):
    def __init__(
        self,
        hits: Sequence[RetrievalHit],
        error: Exception | None = None,
    ) -> None:
        self.hits = tuple(hits)
        self.error = error
        self.queries: list[str] = []

    @override
    async def retrieve(
        self,
        query: str,
        *,
        limit: int,
        tenant_id: str | None,
        namespace: str | None,
        filters: JsonObject,
    ) -> Sequence[RetrievalHit]:
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return self.hits


class RetrievalModel(IAgentModel):
    def __init__(
        self,
        *,
        use_tool: bool = False,
        tool_name: str = "search",
        tool_arguments: JsonObject | None = None,
    ) -> None:
        self.use_tool = use_tool
        self.tool_name = tool_name
        self.tool_arguments = (
            {"query": "agent question"} if tool_arguments is None else tool_arguments
        )
        self.requests: list[ModelRequest] = []

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability(supports_tools=True, supports_structured_output=True)

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="unused")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        if self.use_tool and len(self.requests) == 1:
            yield ModelStreamEvent(
                kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
                tool_call=ModelToolCall(
                    self.tool_name,
                    self.tool_arguments,
                    "retrieval-call",
                ),
            )
            yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)
            return
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.STRUCTURED_OUTPUT,
            structured_output={"answer": "grounded"},
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


@Agent(
    spec=AgentExecutionSpec(
        name="classic_retrieval",
        output_type=Answer,
        recovery=RecoveryStrategy.ACTION_BOUNDARY,
    )
)
class ClassicRetrievalAgent:
    def __init__(
        self,
        model: IAgentModel,
        retrieval: RetrievalContext,
        states: FakeStateRepository,
        signals: FakeSignalRepository,
        evidence: FakeEvidenceRepository,
    ) -> None:
        self._model = model
        self._retrieval = retrieval
        self._states = states
        self._signals = signals
        self._evidence = evidence


@Agent(spec=AgentExecutionSpec(name="agentic_retrieval", output_type=Answer))
class AgenticRetrievalAgent:
    def __init__(self, model: IAgentModel, retrieval: RetrievalTool) -> None:
        self._model = model
        self._retrieval = retrieval


@Agent(spec=AgentExecutionSpec(name="retrieval_collision", output_type=Answer))
class RetrievalCollisionAgent:
    def __init__(self, model: IAgentModel, retrieval: RetrievalTool) -> None:
        self._model = model
        self._retrieval = retrieval

    @agent_tool(
        schema_name="search",
        effects=ToolEffects.read_only(),
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def native_search(self, query: str) -> str:
        return query


class MarkerToolProvider(IAgentToolProvider):
    class_marker = "provider-class-marker"

    def __init__(self) -> None:
        self.marker = "provider-instance-marker"
        self.calls = 0
        self._tool_catalog = discover_agent_tools(type(self))

    @property
    @override
    def tool_catalog(self) -> AgentToolCatalog:
        return self._tool_catalog

    @agent_tool(
        schema_name="provider.marker",
        effects=ToolEffects.read_only(),
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def read_marker(self) -> str:
        self.calls += 1
        return self.marker

    @classmethod
    @agent_tool(
        schema_name="provider.class_marker",
        effects=ToolEffects.read_only(),
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def read_class_marker(cls) -> str:
        return cls.class_marker


class ForeignOwnerToolProvider(IAgentToolProvider):
    def __init__(self) -> None:
        self._tool_catalog = discover_agent_tools(MarkerToolProvider)

    @property
    @override
    def tool_catalog(self) -> AgentToolCatalog:
        return self._tool_catalog


class BoundCallableToolProvider(MarkerToolProvider):
    def __init__(self) -> None:
        super().__init__()
        descriptor = next(
            item
            for item in self._tool_catalog.descriptors
            if item.schema.name == "provider.marker"
        )
        self._tool_catalog = AgentToolCatalog(
            descriptors=(replace(descriptor, callable=self.read_marker),)
        )


@Agent(spec=AgentExecutionSpec(name="injected_tool_provider", output_type=Answer))
class InjectedToolProviderAgent:
    def __init__(self, model: IAgentModel, provider: IAgentToolProvider) -> None:
        self._model = model
        self._provider = provider


def _hit(content: str = "context " * 100) -> RetrievalHit:
    return RetrievalHit(
        "hit-1",
        content,
        "kb:article-1",
        score=0.6,
        rerank_score=0.8,
        content_digest="sha256:one",
        revision="r1",
        tenant_id="tenant-1",
        namespace="support",
        start_offset=10,
        end_offset=20,
        metadata={"raw_secret": "must-not-leak"},
    )


async def test_classic_rag_retrieval_becomes_budgeted_context_and_typed_final() -> None:
    retriever = AcceptanceRetriever((_hit(),))
    retrieval = RetrievalContext(
        retriever,
        max_context_tokens=50,
        tenant_id="tenant-1",
        namespace="support",
    )
    model = RetrievalModel()
    states = FakeStateRepository()
    evidence = FakeEvidenceRepository()
    runner = AgentRunner.for_agent_instance(
        ClassicRetrievalAgent(
            model,
            retrieval,
            states,
            FakeSignalRepository(()),
            evidence,
        )
    )

    items = [
        item
        async for item in runner.run(
            RunAgentInput(state_id="classic", instruction="customer question")
        )
    ]

    final = items[-1].payload
    assert isinstance(final, Final)
    assert final.output == Answer(answer="grounded")
    request = model.requests[0]
    assert len(request.context) == 1
    assert request.context_manifest is not None
    assert request.context_manifest.entries[0].evidence_ref == "hit-1"
    truncation = cast(
        Mapping[str, object],
        request.context[0].metadata["context_truncation"],
    )
    assert truncation["truncated"] is True
    assembled = request.assemble_messages()
    assert assembled[-1].role is ModelMessageRole.EVIDENCE
    assert "customer question" not in assembled[-1].content
    artifacts = evidence.list_by_state("classic")
    context_evidence = next(
        item for item in artifacts if item.kind is AgentEvidenceKind.CONTEXT
    )
    serialized = repr(context_evidence.payload)
    assert "must-not-leak" not in serialized
    assert "context context" not in serialized
    assert "hit-1" in serialized
    assert "rerank_score" in serialized
    assert states.get("classic").status is AgentStatus.COMPLETED


@pytest.mark.parametrize("surface", ["run", "events"])
async def test_classic_rag_retrieval_failure_is_typed(surface: str) -> None:
    retrieval = RetrievalContext(AcceptanceRetriever(()))
    model = RetrievalModel()
    states = FakeStateRepository()
    target = ClassicRetrievalAgent(
        model,
        retrieval,
        states,
        FakeSignalRepository(()),
        FakeEvidenceRepository(),
    )
    runner = AgentRunner.for_agent_instance(target)
    command = RunAgentInput(state_id=f"empty-{surface}", instruction="question")

    if surface == "events":
        events = [event async for event in runner.run_events(command)]
        terminal = events[-1]
        assert isinstance(terminal, RunFinishedEvent)
        assert terminal.error is not None
        assert terminal.error["code"] == "agent_model_execution_failed"
    else:
        items = [item async for item in runner.run(command)]
        error = items[-1].payload
        assert isinstance(error, Error)
        assert error.code == "agent_model_execution_failed"
    assert states.get(f"empty-{surface}").reason is AgentStateReason.EXECUTION_FAILED
    assert model.requests == []


async def test_classic_rag_allow_empty_opt_in_reaches_model() -> None:
    retrieval = RetrievalContext(AcceptanceRetriever(()), allow_empty=True)
    model = RetrievalModel()
    runner = AgentRunner.for_agent_instance(
        ClassicRetrievalAgent(
            model,
            retrieval,
            FakeStateRepository(),
            FakeSignalRepository(()),
            FakeEvidenceRepository(),
        )
    )
    items = [
        item
        async for item in runner.run(
            RunAgentInput(state_id="allow-empty", instruction="question")
        )
    ]
    assert items[-1].kind is AgentYieldKind.FINAL
    assert model.requests[0].context == ()


async def test_agentic_rag_injected_tool_continues_through_tool_history() -> None:
    retriever = AcceptanceRetriever((_hit("agentic result"),))
    tool = RetrievalTool(
        retriever,
        tenant_id="tenant-1",
        namespace="support",
    )
    model = RetrievalModel(use_tool=True)
    runner = AgentRunner.for_agent_instance(AgenticRetrievalAgent(model, tool))

    items = [
        item
        async for item in runner.run(
            RunAgentInput(state_id="agentic", instruction="use retrieval")
        )
    ]

    assert model.requests[0].tool_calling is not None
    assert [spec.name for spec in model.requests[0].tool_calling.tools] == ["search"]
    tool_item = next(item.payload for item in items if isinstance(item.payload, Tool))
    assert tool_item.arguments == {"query": "agent question"}
    assert tool_item.metadata["tool_identity"]
    tool_history = next(
        message
        for message in model.requests[1].messages
        if message.role is ModelMessageRole.TOOL
    )
    assert "agentic result" in tool_history.content
    assert "raw_secret" not in tool_history.content
    final = items[-1].payload
    assert isinstance(final, Final)
    assert final.output == Answer(answer="grounded")


async def test_injected_provider_instance_tool_executes_on_provider() -> None:
    provider = MarkerToolProvider()
    model = RetrievalModel(
        use_tool=True,
        tool_name="provider.marker",
        tool_arguments={},
    )
    shared = Agent.get(InjectedToolProviderAgent)
    runner = AgentRunner.for_agent_instance(InjectedToolProviderAgent(model, provider))

    items = [
        item
        async for item in runner.run(
            RunAgentInput(state_id="provider-tool", instruction="read marker")
        )
    ]

    assert provider.calls == 1
    assert [item.schema.name for item in shared.tool_catalog.descriptors] == []
    assert model.requests[0].tool_calling is not None
    assert {item.name for item in model.requests[0].tool_calling.tools} == {
        "provider.class_marker",
        "provider.marker",
    }
    tool_history = next(
        message
        for message in model.requests[1].messages
        if message.role is ModelMessageRole.TOOL
    )
    assert "provider-instance-marker" in tool_history.content
    assert isinstance(items[-1].payload, Final)


async def test_agentic_rag_nonstring_query_is_typed_tool_failure() -> None:
    retriever = AcceptanceRetriever((_hit(),))
    model = RetrievalModel(use_tool=True, tool_arguments={"query": 1})
    runner = AgentRunner.for_agent_instance(
        AgenticRetrievalAgent(
            model,
            RetrievalTool(
                retriever,
                tenant_id="tenant-1",
                namespace="support",
            ),
        )
    )

    items = [
        item
        async for item in runner.run(
            RunAgentInput(state_id="bad-query", instruction="use retrieval")
        )
    ]

    error = items[-1].payload
    assert isinstance(error, Error)
    assert error.code == "agent_tool_execution_failed"
    assert retriever.queries == []


def test_injected_retrieval_tool_collision_does_not_mutate_shared_agent() -> None:
    tool = RetrievalTool(AcceptanceRetriever((_hit(),)))
    target = RetrievalCollisionAgent(RetrievalModel(), tool)
    shared = Agent.get(RetrievalCollisionAgent)
    assert [item.schema.name for item in shared.tool_catalog.descriptors] == ["search"]

    with pytest.raises(AgentDefinitionError):
        AgentRunner.for_agent_instance(target)

    assert [item.schema.name for item in shared.tool_catalog.descriptors] == ["search"]


@pytest.mark.parametrize(
    "provider",
    [ForeignOwnerToolProvider(), BoundCallableToolProvider()],
)
def test_injected_tool_provider_rejects_wrong_owner_or_callable_shape(
    provider: IAgentToolProvider,
) -> None:
    with pytest.raises(AgentDefinitionError):
        AgentRunner.for_agent_instance(
            InjectedToolProviderAgent(RetrievalModel(), provider)
        )
