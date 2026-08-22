"""Tests for minimal retrieval context, tool, vector, and reranking contracts."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from math import inf
from typing import cast, override

import pytest

import spakky.agent as public_api
from spakky.agent import (
    AgentRetrievalError,
    AgentToolDispatcher,
    EmbeddingPurpose,
    EmbeddingVector,
    IAgentToolProvider,
    IReranker,
    IRetriever,
    ITextEmbedding,
    IVectorSearch,
    ModelToolCall,
    RerankedRetriever,
    RetrievalContext,
    RetrievalHit,
    RetrievalTool,
    RunAgentInput,
    VectorRetriever,
)
from spakky.agent.retrieval import _validated_hits
from spakky.agent.runner import _tool_result_json


class RecordingRetriever(IRetriever):
    def __init__(self, hits: Sequence[RetrievalHit]) -> None:
        self.hits = tuple(hits)
        self.calls: list[tuple[str, int, str | None, str | None, object]] = []

    @override
    async def retrieve(
        self,
        query: str,
        *,
        limit: int,
        tenant_id: str | None,
        namespace: str | None,
        filters: public_api.JsonObject,
    ) -> Sequence[RetrievalHit]:
        self.calls.append((query, limit, tenant_id, namespace, filters))
        return self.hits


def _hit(identifier: str = "hit-1", content: str = "retrieved") -> RetrievalHit:
    return RetrievalHit(
        identifier,
        content,
        "source:1",
        score=0.7,
        rerank_score=0.9,
        content_digest="sha256:hit",
        revision="rev-1",
        tenant_id="tenant-1",
        namespace="support",
        start_offset=0,
        end_offset=9,
        metadata={"raw": "omitted"},
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: RetrievalHit(cast(str, 1), "content", "source"),
        lambda: RetrievalHit(" ", "content", "source"),
        lambda: RetrievalHit("id\nframe", "content", "source"),
        lambda: RetrievalHit("id", cast(str, 1), "source"),
        lambda: RetrievalHit("id", " ", "source"),
        lambda: RetrievalHit("id", "content", cast(str, 1)),
        lambda: RetrievalHit("id", "content", "source\rframe"),
        lambda: RetrievalHit("id", "content", "source", score=True),
        lambda: RetrievalHit(
            "id",
            "content",
            "source",
            rerank_score=cast(float, "bad"),
        ),
        lambda: RetrievalHit("id", "content", "source", score=inf),
        lambda: RetrievalHit(
            "id",
            "content",
            "source",
            content_digest=cast(str, 1),
        ),
        lambda: RetrievalHit(
            "id",
            "content",
            "source",
            revision=cast(str, 1),
        ),
        lambda: RetrievalHit(
            "id",
            "content",
            "source",
            tenant_id=cast(str, 1),
        ),
        lambda: RetrievalHit(
            "id",
            "content",
            "source",
            namespace=cast(str, 1),
        ),
        lambda: RetrievalHit(
            "id",
            "content",
            "source",
            start_offset=True,
            end_offset=1,
        ),
        lambda: RetrievalHit(
            "id",
            "content",
            "source",
            start_offset=cast(int, "bad"),
            end_offset=1,
        ),
        lambda: RetrievalHit("id", "content", "source", start_offset=0),
        lambda: RetrievalHit("id", "content", "source", start_offset=2, end_offset=1),
    ],
)
def test_retrieval_hit_rejects_invalid_identity_score_span_and_framing(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(AgentRetrievalError):
        factory()


def test_retrieval_hit_allows_unscored_unspanned_content() -> None:
    hit = RetrievalHit("id", "content", "source")
    assert hit.score is None
    assert hit.start_offset is None


@pytest.mark.parametrize("value", [True, 1.5, "1", 0, -1])
def test_retrieval_context_and_tool_reject_invalid_limits(value: object) -> None:
    retriever = RecordingRetriever(())
    with pytest.raises(AgentRetrievalError):
        RetrievalContext(retriever, limit=cast(int, value))
    with pytest.raises(AgentRetrievalError):
        RetrievalContext(retriever, max_context_tokens=cast(int, value))
    with pytest.raises(AgentRetrievalError):
        RetrievalTool(retriever, limit=cast(int, value))


async def test_retrieval_context_builds_scoped_budgeted_packs_and_manifest() -> None:
    retriever = RecordingRetriever((_hit(), _hit("hit-2", "second")))
    provider = RetrievalContext(
        retriever,
        limit=2,
        max_context_tokens=20,
        tenant_id="tenant-1",
        namespace="support",
        filters={"kind": "faq"},
    )

    context = await provider.provide(
        RunAgentInput(state_id="run", instruction="How?"),
        1,
    )

    assert retriever.calls == [("How?", 2, "tenant-1", "support", {"kind": "faq"})]
    assert [pack.id for pack in context.packs] == ["retrieval:hit-1"]
    assert context.packs[0].content.startswith('{"retrieval":')
    assert context.packs[0].token_budget.max_tokens == 20
    estimated = context.packs[0].token_budget.estimated_tokens
    assert estimated is not None and estimated > 20
    retrieval_metadata = cast(
        Mapping[str, public_api.JsonValue],
        context.packs[0].metadata["retrieval"],
    )
    assert retrieval_metadata["score"] == 0.7
    assert context.manifest is not None
    entry = context.manifest.entries[0]
    assert entry.evidence_ref == "hit-1"
    assert entry.digest_ref == "sha256:hit"


async def test_retrieval_context_empty_scope_and_duplicate_fail_closed() -> None:
    command = RunAgentInput(state_id="run", instruction="query")
    with pytest.raises(AgentRetrievalError):
        await RetrievalContext(RecordingRetriever(())).provide(command, 1)
    assert (
        await RetrievalContext(RecordingRetriever(()), allow_empty=True).provide(
            command, 1
        )
    ).packs == ()
    with pytest.raises(AgentRetrievalError):
        await RetrievalContext(
            RecordingRetriever((_hit(), _hit())),
            tenant_id="tenant-1",
            namespace="support",
        ).provide(command, 1)
    with pytest.raises(AgentRetrievalError):
        await RetrievalContext(
            RecordingRetriever((replace(_hit(), tenant_id="x"),)),
            tenant_id="tenant-1",
        ).provide(command, 1)
    with pytest.raises(AgentRetrievalError):
        await RetrievalContext(
            RecordingRetriever((replace(_hit(), namespace="x"),)),
            tenant_id="tenant-1",
            namespace="support",
        ).provide(command, 1)


async def test_retrieval_scope_requires_exact_match_in_both_directions() -> None:
    command = RunAgentInput(state_id="run", instruction="query")
    scoped = _hit()
    unscoped = replace(scoped, tenant_id=None, namespace=None)

    for provider in (
        RetrievalContext(RecordingRetriever((scoped,))),
        RetrievalContext(
            RecordingRetriever((unscoped,)),
            tenant_id="tenant-1",
            namespace="support",
        ),
    ):
        with pytest.raises(AgentRetrievalError):
            await provider.provide(command, 1)

    tool = RetrievalTool(RecordingRetriever((scoped,)))
    with pytest.raises(AgentRetrievalError):
        await AgentToolDispatcher(object(), tool.tool_catalog).dispatch(
            ModelToolCall("search", {"query": "query"}, "call")
        )
    with pytest.raises(AgentRetrievalError):
        await VectorRetriever(
            RecordingEmbedding(),
            RecordingVectorSearch((scoped,)),
        ).retrieve(
            "query",
            limit=1,
            tenant_id=None,
            namespace=None,
            filters={},
        )
    with pytest.raises(AgentRetrievalError):
        await RerankedRetriever(
            RecordingRetriever((scoped,)),
            ReorderingReranker(),
        ).retrieve(
            "query",
            limit=1,
            tenant_id=None,
            namespace=None,
            filters={},
        )


async def test_fixed_filters_are_deep_snapshotted_for_context_and_tool() -> None:
    nested: dict[str, public_api.JsonValue] = {"value": 1}
    filters: dict[str, public_api.JsonValue] = {"nested": nested}
    context_retriever = RecordingRetriever((_hit(),))
    context = RetrievalContext(
        context_retriever,
        tenant_id="tenant-1",
        namespace="support",
        filters=filters,
    )
    tool_retriever = RecordingRetriever((_hit(),))
    tool = RetrievalTool(
        tool_retriever,
        tenant_id="tenant-1",
        namespace="support",
        filters=filters,
    )
    nested["value"] = 2

    await context.provide(RunAgentInput(state_id="run", instruction="query"), 1)
    await AgentToolDispatcher(object(), tool.tool_catalog).dispatch(
        ModelToolCall("search", {"query": "query"}, "call")
    )

    assert context_retriever.calls[0][-1] == {"nested": {"value": 1}}
    assert tool_retriever.calls[0][-1] == {"nested": {"value": 1}}


@pytest.mark.parametrize("factory", [RetrievalContext, RetrievalTool])
def test_fixed_filters_reject_nonfinite_values(factory: Callable[..., object]) -> None:
    with pytest.raises(AgentRetrievalError):
        factory(RecordingRetriever(()), filters={"score": inf})


@pytest.mark.parametrize(
    "filters",
    [
        ["not-an-object"],
        {1: "bad"},
        {"value": object()},
        {"values": [1, 2], "weight": 1.5},
    ],
)
def test_fixed_filters_validate_recursive_json_values(filters: object) -> None:
    if filters == {"values": [1, 2], "weight": 1.5}:
        context = RetrievalContext(
            RecordingRetriever(()),
            allow_empty=True,
            filters=cast(public_api.JsonObject, filters),
        )
        assert context.filters == {"values": [1, 2], "weight": 1.5}
        return
    with pytest.raises(AgentRetrievalError):
        RetrievalContext(
            RecordingRetriever(()),
            filters=cast(public_api.JsonObject, filters),
        )


async def test_retrieval_tool_exposes_query_only_and_omits_arbitrary_metadata() -> None:
    retriever = RecordingRetriever((_hit(),))
    tool = RetrievalTool(
        retriever,
        name="knowledge_search",
        tenant_id="tenant-1",
        namespace="support",
    )
    descriptor = tool.tool_catalog.descriptors[0]

    result = await AgentToolDispatcher(
        target=object(),
        catalog=tool.tool_catalog,
    ).dispatch(ModelToolCall("knowledge_search", {"query": "question"}, "call-1"))
    serialized = _tool_result_json(result)

    assert isinstance(tool, IAgentToolProvider)
    assert descriptor.schema.name == "knowledge_search"
    properties = cast(
        Mapping[str, public_api.JsonValue],
        descriptor.schema.input_schema["properties"],
    )
    assert set(properties) == {"query"}
    assert serialized == [
        {
            "id": "hit-1",
            "score": 0.7,
            "rerank_score": 0.9,
            "content_digest": "sha256:hit",
            "revision": "rev-1",
            "tenant_id": "tenant-1",
            "namespace": "support",
            "start_offset": 0,
            "end_offset": 9,
            "content": "retrieved",
            "source": "source:1",
        }
    ]


class RecordingEmbedding(ITextEmbedding):
    def __init__(self) -> None:
        self.calls: list[tuple[Sequence[str], EmbeddingPurpose]] = []

    @override
    async def embed(
        self,
        texts: Sequence[str],
        purpose: EmbeddingPurpose,
    ) -> Sequence[EmbeddingVector]:
        self.calls.append((texts, purpose))
        return (EmbeddingVector((1.0, 0.0), normalized=True),)


class RecordingVectorSearch(IVectorSearch):
    def __init__(self, hits: Sequence[RetrievalHit]) -> None:
        self.hits = hits
        self.vector: EmbeddingVector | None = None

    @override
    async def search(
        self,
        vector: EmbeddingVector,
        *,
        limit: int,
        tenant_id: str | None,
        namespace: str | None,
        filters: public_api.JsonObject,
    ) -> Sequence[RetrievalHit]:
        self.vector = vector
        return self.hits


async def test_vector_retriever_uses_exact_query_embedding_batch() -> None:
    embedding = RecordingEmbedding()
    search = RecordingVectorSearch((_hit(),))

    hits = await VectorRetriever(embedding, search).retrieve(
        "query",
        limit=3,
        tenant_id="tenant-1",
        namespace="support",
        filters={},
    )

    assert embedding.calls == [(("query",), EmbeddingPurpose.QUERY)]
    assert search.vector == EmbeddingVector((1.0, 0.0), normalized=True)
    assert hits == (_hit(),)


class ReorderingReranker(IReranker):
    def __init__(self, *, invent: bool = False, mutate: bool = False) -> None:
        self.invent = invent
        self.mutate = mutate

    @override
    async def rerank(
        self,
        query: str,
        hits: Sequence[RetrievalHit],
        *,
        limit: int,
    ) -> Sequence[RetrievalHit]:
        if self.invent:
            return (_hit("invented"),)
        if self.mutate:
            return (replace(hits[0], source="changed"),)
        return tuple(
            replace(hit, rerank_score=float(index + 1))
            for index, hit in enumerate(reversed(hits))
        )


async def test_reranked_retriever_reorders_without_mutating_provenance() -> None:
    base = RecordingRetriever((_hit("one"), _hit("two")))
    reranked = RerankedRetriever(base, ReorderingReranker())

    hits = await reranked.retrieve(
        "query",
        limit=2,
        tenant_id="tenant-1",
        namespace="support",
        filters={},
    )

    assert [hit.id for hit in hits] == ["two", "one"]
    assert [hit.rerank_score for hit in hits] == [1.0, 2.0]
    for reranker in (ReorderingReranker(invent=True), ReorderingReranker(mutate=True)):
        with pytest.raises(AgentRetrievalError):
            await RerankedRetriever(base, reranker).retrieve(
                "query",
                limit=2,
                tenant_id="tenant-1",
                namespace="support",
                filters={},
            )


def test_retrieval_public_exports_are_canonical() -> None:
    from spakky.agent.retrieval import RetrievalHit as DirectHit

    assert public_api.RetrievalHit is DirectHit
    assert public_api.IRetriever is IRetriever


@pytest.mark.parametrize("results", [object(), ("bad",)])
def test_retrieval_result_boundary_rejects_nonsequence_and_nonhit(
    results: object,
) -> None:
    with pytest.raises(AgentRetrievalError):
        _validated_hits(results, limit=1, tenant_id=None, namespace=None)


@pytest.mark.parametrize(
    "values",
    [(), (True,), (inf,), cast(tuple[float, ...], ("bad",))],
)
def test_embedding_vector_rejects_empty_bool_nonnumber_and_nonfinite(
    values: tuple[float, ...],
) -> None:
    with pytest.raises(AgentRetrievalError):
        EmbeddingVector(values)


def test_embedding_vector_is_frozen_and_preserves_numeric_tuple() -> None:
    vector = EmbeddingVector((1, 2.5))
    assert vector.values == (1, 2.5)
    assert vector.dimension == 2


async def test_vector_and_reranked_retrievers_reject_invalid_requests() -> None:
    embedding = RecordingEmbedding()
    search = RecordingVectorSearch((_hit(),))
    vector = VectorRetriever(embedding, search)
    reranked = RerankedRetriever(RecordingRetriever((_hit(),)), ReorderingReranker())
    for retriever in (vector, reranked):
        for query, limit in (
            (" ", 1),
            (cast(str, 1), 1),
            ("query", 0),
            ("query", cast(int, True)),
            ("query", cast(int, 1.5)),
        ):
            with pytest.raises(AgentRetrievalError):
                await retriever.retrieve(
                    query,
                    limit=limit,
                    tenant_id=None,
                    namespace=None,
                    filters={},
                )


class InvalidEmbedding(ITextEmbedding):
    def __init__(self, result: object) -> None:
        self.result = result

    @override
    async def embed(
        self,
        texts: Sequence[str],
        purpose: EmbeddingPurpose,
    ) -> Sequence[EmbeddingVector]:
        return cast(Sequence[EmbeddingVector], self.result)


@pytest.mark.parametrize("result", [object(), (), ("bad",)])
async def test_vector_retriever_rejects_invalid_embedding_result(
    result: object,
) -> None:
    retriever = VectorRetriever(InvalidEmbedding(result), RecordingVectorSearch(()))
    with pytest.raises(AgentRetrievalError):
        await retriever.retrieve(
            "query", limit=1, tenant_id=None, namespace=None, filters={}
        )


@pytest.mark.parametrize("query", [" ", 1])
async def test_retrieval_tool_rejects_invalid_model_query(query: object) -> None:
    tool = RetrievalTool(RecordingRetriever(()))
    with pytest.raises(AgentRetrievalError):
        await AgentToolDispatcher(object(), tool.tool_catalog).dispatch(
            ModelToolCall(
                "search",
                {"query": cast(public_api.JsonValue, query)},
                "call",
            )
        )
