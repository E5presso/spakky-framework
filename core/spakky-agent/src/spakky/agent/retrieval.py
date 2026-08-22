"""Minimal retrieval contracts for classic and agentic RAG."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from hashlib import sha256
from json import dumps, loads
from math import isfinite
from typing import cast

from spakky.agent.context import (
    AgentContext,
    ContextFreshness,
    ContextManifest,
    ContextManifestEntry,
    ContextPack,
    ContextPackRole,
    ContextTokenBudget,
    IAgentContextProvider,
)
from spakky.agent.error import AgentRetrievalError
from spakky.agent.inbound import RunAgentInput
from spakky.agent.tooling import (
    AgentToolCatalog,
    AgentToolDefinition,
    AgentToolMetadata,
    EvidenceCapture,
    IAgentToolProvider,
    Idempotency,
    ToolApprovalRequirement,
    ToolEffects,
    _build_descriptor,
)
from spakky.agent.types import JsonObject

_CHARACTERS_PER_TOKEN = 4


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    """One retrieved model-facing text result with typed provenance."""

    id: str
    content: str
    source: str
    score: float | None = None
    rerank_score: float | None = None
    content_digest: str | None = None
    revision: str | None = None
    tenant_id: str | None = None
    namespace: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_framing_text(self.id, "Retrieval hit id")
        if not isinstance(self.content, str) or not self.content.strip():
            raise AgentRetrievalError("Retrieval hit content cannot be blank")
        _require_framing_text(self.source, "Retrieval hit source")
        for value in (self.score, self.rerank_score):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not isfinite(value)
            ):
                raise AgentRetrievalError("Retrieval hit score must be finite numeric")
        for value, label in (
            (self.content_digest, "Retrieval hit content digest"),
            (self.revision, "Retrieval hit revision"),
            (self.tenant_id, "Retrieval hit tenant id"),
            (self.namespace, "Retrieval hit namespace"),
        ):
            if value is not None:
                _require_framing_text(value, label)
        for value in (self.start_offset, self.end_offset):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int)
            ):
                raise AgentRetrievalError("Retrieval hit offsets must be integers")
        if (self.start_offset is None) != (self.end_offset is None):
            raise AgentRetrievalError("Retrieval hit span must declare both offsets")
        if self.start_offset is not None and self.end_offset is not None:
            if self.start_offset < 0 or self.end_offset <= self.start_offset:
                raise AgentRetrievalError("Retrieval hit span is invalid")


class IRetriever(ABC):
    """Async retrieval port shared by context and tool adapters."""

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        *,
        limit: int,
        tenant_id: str | None,
        namespace: str | None,
        filters: JsonObject,
    ) -> Sequence[RetrievalHit]:
        """Return ordered retrieval hits for one scoped query."""
        ...


@dataclass(frozen=True, slots=True)
class _RetrievalToolHit:
    id: str
    content: str
    source: str
    score: float | None
    rerank_score: float | None
    content_digest: str | None
    revision: str | None
    tenant_id: str | None
    namespace: str | None
    start_offset: int | None
    end_offset: int | None


@dataclass(slots=True)
class RetrievalContext(IAgentContextProvider):
    """Classic RAG adapter exposing retrieval as typed model context."""

    retriever: IRetriever
    limit: int = 5
    max_context_tokens: int = 2048
    allow_empty: bool = False
    tenant_id: str | None = None
    namespace: str | None = None
    filters: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.limit = _positive_limit(self.limit, "Retrieval context limit")
        self.max_context_tokens = _positive_limit(
            self.max_context_tokens,
            "Retrieval context token budget",
        )
        _validate_scope(self.tenant_id, self.namespace)
        self.filters = _snapshot_filters(self.filters)

    async def provide(self, run_input: RunAgentInput, model_step: int) -> AgentContext:
        _ = model_step
        results = await self.retriever.retrieve(
            run_input.instruction,
            limit=self.limit,
            tenant_id=self.tenant_id,
            namespace=self.namespace,
            filters=_snapshot_filters(self.filters),
        )
        hits = _validated_hits(
            results,
            limit=self.limit,
            tenant_id=self.tenant_id,
            namespace=self.namespace,
        )
        if not hits:
            if self.allow_empty:
                return AgentContext()
            raise AgentRetrievalError("Retrieval returned no hits")
        packs = _context_packs(hits, self.max_context_tokens)
        selected = hits[: len(packs)]
        manifest = ContextManifest(
            id=_manifest_id(selected, packs),
            entries=tuple(
                ContextManifestEntry(
                    pack_id=pack.id,
                    source=hit.source,
                    role=ContextPackRole.EVIDENCE,
                    origin_ref=hit.source,
                    evidence_ref=hit.id,
                    digest_ref=hit.content_digest,
                )
                for hit, pack in zip(selected, packs, strict=True)
            ),
            origin_ref="retrieval",
        )
        return AgentContext(packs=packs, manifest=manifest)


class RetrievalTool(IAgentToolProvider):
    """Agentic RAG component contributing one retrieval tool."""

    def __init__(
        self,
        retriever: IRetriever,
        *,
        name: str = "search",
        limit: int = 5,
        tenant_id: str | None = None,
        namespace: str | None = None,
        filters: JsonObject | None = None,
    ) -> None:
        _require_framing_text(name, "Retrieval tool name")
        limit = _positive_limit(limit, "Retrieval tool limit")
        _validate_scope(tenant_id, namespace)
        self._retriever = retriever
        self._name = name
        self._limit = limit
        self._tenant_id = tenant_id
        self._namespace = namespace
        self._filters = _snapshot_filters({} if filters is None else filters)

        async def invoke(query: str) -> list[_RetrievalToolHit]:
            return await self._invoke(query)

        definition = AgentToolDefinition(
            name=name,
            schema_name=name,
            description="Search scoped retrieval context.",
            metadata=AgentToolMetadata(
                effects=ToolEffects.read_only(),
                idempotency=Idempotency.IDEMPOTENT,
                evidence=EvidenceCapture.STRUCTURED,
                approval=ToolApprovalRequirement.NOT_REQUIRED,
            ),
        )
        self._tool_catalog = AgentToolCatalog(
            descriptors=(_build_descriptor(type(self), invoke, definition),)
        )

    @property
    def tool_catalog(self) -> AgentToolCatalog:
        return self._tool_catalog

    async def _invoke(self, query: str) -> list[_RetrievalToolHit]:
        query = _retrieval_query(query)
        results = await self._retriever.retrieve(
            query,
            limit=self._limit,
            tenant_id=self._tenant_id,
            namespace=self._namespace,
            filters=_snapshot_filters(self._filters),
        )
        hits = _validated_hits(
            results,
            limit=self._limit,
            tenant_id=self._tenant_id,
            namespace=self._namespace,
        )
        return [_tool_hit(hit) for hit in hits]


class EmbeddingPurpose(StrEnum):
    QUERY = "query"
    DOCUMENT = "document"


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    values: tuple[float, ...]
    normalized: bool = False

    def __post_init__(self) -> None:
        if not self.values:
            raise AgentRetrievalError("Embedding vector cannot be empty")
        for value in self.values:
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not isfinite(value)
            ):
                raise AgentRetrievalError(
                    "Embedding vector values must be finite numbers"
                )

    @property
    def dimension(self) -> int:
        return len(self.values)


class ITextEmbedding(ABC):
    @abstractmethod
    async def embed(
        self,
        texts: Sequence[str],
        purpose: EmbeddingPurpose,
    ) -> Sequence[EmbeddingVector]: ...


class IVectorSearch(ABC):
    @abstractmethod
    async def search(
        self,
        vector: EmbeddingVector,
        *,
        limit: int,
        tenant_id: str | None,
        namespace: str | None,
        filters: JsonObject,
    ) -> Sequence[RetrievalHit]: ...


@dataclass(frozen=True, slots=True)
class VectorRetriever(IRetriever):
    embedding: ITextEmbedding
    vector_search: IVectorSearch

    async def retrieve(
        self,
        query: str,
        *,
        limit: int,
        tenant_id: str | None,
        namespace: str | None,
        filters: JsonObject,
    ) -> Sequence[RetrievalHit]:
        query = _retrieval_query(query)
        limit = _positive_limit(limit, "Vector retrieval limit")
        result = await self.embedding.embed((query,), EmbeddingPurpose.QUERY)
        if not isinstance(result, Sequence) or isinstance(result, str | bytes):
            raise AgentRetrievalError("Query embedding result must be a sequence")
        vectors = tuple(result)
        if len(vectors) != 1 or not isinstance(vectors[0], EmbeddingVector):
            raise AgentRetrievalError("Query embedding must return exactly one vector")
        results = await self.vector_search.search(
            vectors[0],
            limit=limit,
            tenant_id=tenant_id,
            namespace=namespace,
            filters=filters,
        )
        return _validated_hits(
            results,
            limit=limit,
            tenant_id=tenant_id,
            namespace=namespace,
        )


class IReranker(ABC):
    @abstractmethod
    async def rerank(
        self,
        query: str,
        hits: Sequence[RetrievalHit],
        *,
        limit: int,
    ) -> Sequence[RetrievalHit]: ...


@dataclass(frozen=True, slots=True)
class RerankedRetriever(IRetriever):
    retriever: IRetriever
    reranker: IReranker

    async def retrieve(
        self,
        query: str,
        *,
        limit: int,
        tenant_id: str | None,
        namespace: str | None,
        filters: JsonObject,
    ) -> Sequence[RetrievalHit]:
        query = _retrieval_query(query)
        limit = _positive_limit(limit, "Reranked retrieval limit")
        base = await self.retriever.retrieve(
            query,
            limit=limit,
            tenant_id=tenant_id,
            namespace=namespace,
            filters=filters,
        )
        validated = _validated_hits(
            base,
            limit=limit,
            tenant_id=tenant_id,
            namespace=namespace,
        )
        reranked = await self.reranker.rerank(query, validated, limit=limit)
        output = _validated_hits(
            reranked,
            limit=limit,
            tenant_id=tenant_id,
            namespace=namespace,
        )
        originals = {hit.id: hit for hit in validated}
        for hit in output:
            original = originals.get(hit.id)
            if original is None:
                raise AgentRetrievalError("Reranker invented a retrieval hit")
            if replace(hit, rerank_score=original.rerank_score) != original:
                raise AgentRetrievalError("Reranker mutated retrieval provenance")
        return output


def _validated_hits(
    results: object,
    *,
    limit: int,
    tenant_id: str | None,
    namespace: str | None,
) -> tuple[RetrievalHit, ...]:
    if not isinstance(results, Sequence) or isinstance(results, str | bytes):
        raise AgentRetrievalError("Retriever result must be a sequence")
    hits: list[RetrievalHit] = []
    seen: set[str] = set()
    for item in results:
        if not isinstance(item, RetrievalHit):
            raise AgentRetrievalError("Retriever returned an invalid hit")
        if item.id in seen:
            raise AgentRetrievalError("Retriever returned duplicate hit ids")
        if item.tenant_id != tenant_id:
            raise AgentRetrievalError("Retriever returned a mismatched tenant scope")
        if item.namespace != namespace:
            raise AgentRetrievalError("Retriever returned a mismatched namespace")
        seen.add(item.id)
        hits.append(item)
    return tuple(hits[:limit])


def _context_packs(
    hits: Sequence[RetrievalHit],
    max_tokens: int,
) -> tuple[ContextPack, ...]:
    remaining_tokens = max_tokens
    packs: list[ContextPack] = []
    for hit in hits:
        prefix = _hit_frame(hit)
        framed = f"{prefix}\n{hit.content}"
        estimated_tokens = max(
            1,
            (len(framed) + _CHARACTERS_PER_TOKEN - 1) // _CHARACTERS_PER_TOKEN,
        )
        allocation = min(remaining_tokens, estimated_tokens)
        packs.append(
            ContextPack(
                id=f"retrieval:{hit.id}",
                content=framed,
                source=hit.source,
                role=ContextPackRole.EVIDENCE,
                freshness=ContextFreshness.CURRENT,
                relevance=hit.rerank_score
                if hit.rerank_score is not None
                else hit.score,
                token_budget=ContextTokenBudget(
                    max_tokens=allocation,
                    estimated_tokens=estimated_tokens,
                ),
                metadata={"retrieval": _hit_reference(hit)},
            )
        )
        remaining_tokens -= allocation
        if remaining_tokens == 0:
            break
    return tuple(packs)


def _manifest_id(hits: Sequence[RetrievalHit], packs: Sequence[ContextPack]) -> str:
    payload = tuple(
        {
            **_hit_reference(hit),
            "pack_id": pack.id,
            "model_content_digest": sha256(pack.content.encode()).hexdigest(),
        }
        for hit, pack in zip(hits, packs, strict=True)
    )
    encoded = dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"retrieval-manifest:{sha256(encoded).hexdigest()}"


def _hit_reference(hit: RetrievalHit) -> JsonObject:
    return {
        "id": hit.id,
        "score": hit.score,
        "rerank_score": hit.rerank_score,
        "content_digest": hit.content_digest,
        "revision": hit.revision,
        "tenant_id": hit.tenant_id,
        "namespace": hit.namespace,
        "start_offset": hit.start_offset,
        "end_offset": hit.end_offset,
    }


def _hit_frame(hit: RetrievalHit) -> str:
    span = "-" if hit.start_offset is None else f"{hit.start_offset}:{hit.end_offset}"
    return dumps(
        {
            "retrieval": {
                "id": hit.id,
                "source": hit.source,
                "revision": hit.revision,
                "content_digest": hit.content_digest,
                "span": span,
                "tenant_id": hit.tenant_id,
                "namespace": hit.namespace,
            }
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _tool_hit(hit: RetrievalHit) -> _RetrievalToolHit:
    return _RetrievalToolHit(
        id=hit.id,
        content=hit.content,
        source=hit.source,
        score=hit.score,
        rerank_score=hit.rerank_score,
        content_digest=hit.content_digest,
        revision=hit.revision,
        tenant_id=hit.tenant_id,
        namespace=hit.namespace,
        start_offset=hit.start_offset,
        end_offset=hit.end_offset,
    )


def _positive_limit(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AgentRetrievalError(f"{label} must be positive")
    return value


def _require_framing_text(value: object, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or "\n" in value
        or "\r" in value
    ):
        raise AgentRetrievalError(f"{label} must be nonblank single-line text")


def _retrieval_query(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgentRetrievalError("Retrieval query must be nonblank text")
    return value


def _validate_scope(tenant_id: str | None, namespace: str | None) -> None:
    if tenant_id is not None:
        _require_framing_text(tenant_id, "Retrieval tenant id")
    if namespace is not None:
        _require_framing_text(namespace, "Retrieval namespace")


def _snapshot_filters(filters: JsonObject) -> JsonObject:
    if not isinstance(filters, Mapping):
        raise AgentRetrievalError("Retrieval filters must be an object")
    _validate_filter_value(filters)
    encoded = dumps(
        filters,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    value: object = loads(encoded)
    return cast(JsonObject, value)


def _validate_filter_value(value: object) -> None:
    if value is None or isinstance(value, str | int | bool):
        return
    if isinstance(value, float):
        if not isfinite(value):
            raise AgentRetrievalError("Retrieval filters must contain finite numbers")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise AgentRetrievalError("Retrieval filter keys must be text")
            _validate_filter_value(item)
        return
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        for item in value:
            _validate_filter_value(item)
        return
    raise AgentRetrievalError("Retrieval filters must be JSON values")
