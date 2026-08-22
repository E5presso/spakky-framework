"""Tests for scoped, backend-replaceable long-term agent memory contracts."""

from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta, tzinfo
from math import inf
from typing import cast, override

import pytest

import spakky.agent as agent_api
from spakky.agent.error import AgentDefinitionError, AgentMemoryError
from spakky.agent.memory import (
    IMemoryStore,
    MemoryEntry,
    MemoryKind,
    MemoryRetriever,
)
from spakky.agent.retrieval import RetrievalHit
from spakky.agent.types import JsonObject, JsonValue

_CREATED = datetime(2025, 1, 1, tzinfo=UTC)
_LATER = datetime(2025, 1, 2, tzinfo=UTC)


class FakeMemoryStore(IMemoryStore):
    """Offline-only memory store fake with explicit delete semantics."""

    def __init__(self, entries: Sequence[MemoryEntry] = ()) -> None:
        self.entries = list(entries)
        self.result_override: object | None = None
        self.deleted: set[str] = set()
        self.search_calls: list[
            tuple[
                str,
                int,
                str,
                str,
                str,
                tuple[MemoryKind, ...],
                JsonObject,
            ]
        ] = []

    @override
    async def save(self, entry: MemoryEntry) -> None:
        self.entries.append(entry)

    @override
    async def search(
        self,
        query: str,
        *,
        limit: int,
        tenant_id: str,
        user_id: str,
        namespace: str,
        kinds: tuple[MemoryKind, ...],
        filters: JsonObject,
    ) -> Sequence[MemoryEntry]:
        self.search_calls.append(
            (query, limit, tenant_id, user_id, namespace, kinds, filters)
        )
        if self.result_override is not None:
            # The fake deliberately violates the port to probe runtime validation.
            return cast(Sequence[MemoryEntry], self.result_override)
        return tuple(entry for entry in self.entries if entry.id not in self.deleted)

    @override
    async def delete(
        self,
        entry_id: str,
        *,
        tenant_id: str,
        user_id: str,
        namespace: str,
    ) -> None:
        assert (tenant_id, user_id, namespace) == (
            "tenant-1",
            "user-1",
            "support",
        )
        self.deleted.add(entry_id)


class NoneOffsetTimezone(tzinfo):
    """Timezone-shaped value whose UTC offset is intentionally undefined."""

    @override
    def utcoffset(self, dt: datetime | None) -> None:
        return None

    @override
    def dst(self, dt: datetime | None) -> None:
        return None

    @override
    def tzname(self, dt: datetime | None) -> str:
        return "none"


def _entry(
    identifier: str = "memory-1",
    *,
    kind: MemoryKind = MemoryKind.SEMANTIC,
    created_at: datetime = _CREATED,
    expires_at: datetime | None = None,
    supersedes: str | None = None,
) -> MemoryEntry:
    return MemoryEntry(
        id=identifier,
        kind=kind,
        content=f"content for {identifier}",
        source="memory:test",
        revision=f"revision:{identifier}",
        content_digest=f"sha256:{identifier}",
        tenant_id="tenant-1",
        user_id="user-1",
        namespace="support",
        created_at=created_at,
        expires_at=expires_at,
        supersedes=supersedes,
    )


def _retriever(
    store: IMemoryStore,
    *,
    kinds: tuple[MemoryKind, ...] = tuple(MemoryKind),
) -> MemoryRetriever:
    return MemoryRetriever(
        store,
        tenant_id="tenant-1",
        user_id="user-1",
        namespace="support",
        kinds=kinds,
    )


def test_memory_entry_expect_exposes_kind_ttl_expiry_and_correction() -> None:
    """A revision carries typed meaning, deterministic TTL, and supersession."""
    entry = _entry(expires_at=_LATER, supersedes="memory-0")

    assert entry.kind is MemoryKind.SEMANTIC
    assert entry.ttl == timedelta(days=1)
    assert entry.is_expired(_CREATED) is False
    assert entry.is_expired(_LATER) is True
    assert _entry().ttl is None
    assert _entry().is_expired() is False


def test_memory_entry_invalid_definitions_expect_agent_definition_error() -> None:
    """Dataclass construction raises only the framework definition error family."""
    # Runtime-boundary probes intentionally violate static annotations.
    factories = (
        lambda: replace(_entry(), id=cast(str, 1)),
        lambda: replace(_entry(), id=" "),
        lambda: replace(_entry(), id="line\nbreak"),
        lambda: replace(_entry(), id="line\rbreak"),
        lambda: replace(_entry(), kind=cast(MemoryKind, "invalid")),
        lambda: replace(_entry(), content=cast(str, 1)),
        lambda: replace(_entry(), content=" "),
        lambda: replace(_entry(), created_at=cast(datetime, "invalid")),
        lambda: replace(_entry(), created_at=datetime(2025, 1, 1)),
        lambda: replace(
            _entry(),
            created_at=datetime(2025, 1, 1, tzinfo=NoneOffsetTimezone()),
        ),
        lambda: replace(
            _entry(),
            expires_at=datetime(2025, 1, 2),
        ),
        lambda: _entry(expires_at=_CREATED),
        lambda: replace(_entry(), supersedes=" "),
        lambda: replace(_entry(), supersedes="memory-1"),
    )
    for factory in factories:
        with pytest.raises(AgentDefinitionError):
            factory()


def test_memory_entry_naive_expiry_check_expect_agent_memory_error() -> None:
    """A runtime expiry check cannot compare an ambiguous naive timestamp."""
    with pytest.raises(AgentMemoryError):
        _entry(expires_at=_LATER).is_expired(datetime(2025, 1, 1))


def test_memory_public_exports_expect_canonical_identity() -> None:
    """The package root exposes the typed seam without a production fallback."""
    assert agent_api.MemoryEntry is MemoryEntry
    assert agent_api.MemoryKind is MemoryKind
    assert agent_api.MemoryRetriever is MemoryRetriever
    assert agent_api.IMemoryStore is IMemoryStore
    assert agent_api.AgentMemoryError is AgentMemoryError


async def test_memory_retriever_expect_exact_scope_active_revision_and_provenance() -> (
    None
):
    """Expired, corrected, and explicitly deleted revisions never become hits."""
    original = _entry("memory-original")
    correction_expiry = datetime(2100, 1, 1, tzinfo=UTC)
    correction = _entry(
        "memory-correction",
        expires_at=correction_expiry,
        supersedes=original.id,
    )
    independent = _entry("memory-independent", kind=MemoryKind.USER)
    expired = _entry(
        "memory-expired",
        created_at=datetime(2000, 1, 1, tzinfo=UTC),
        expires_at=datetime(2001, 1, 1, tzinfo=UTC),
    )
    deleted = _entry("memory-deleted")
    store = FakeMemoryStore((original, correction, independent, expired, deleted))
    await store.delete(
        deleted.id,
        tenant_id="tenant-1",
        user_id="user-1",
        namespace="support",
    )
    nested: dict[str, JsonValue] = {"value": 1}
    filters: dict[str, JsonValue] = {
        "nested": nested,
        "values": (None, "text", True, 1.5),
    }

    hits = await _retriever(store).retrieve(
        "remembered preference",
        limit=5,
        tenant_id="tenant-1",
        namespace="support",
        filters=filters,
    )
    nested["value"] = 2

    assert hits == (
        RetrievalHit(
            id=correction.id,
            content=correction.content,
            source=correction.source,
            content_digest=correction.content_digest,
            revision=correction.revision,
            tenant_id="tenant-1",
            namespace="support",
            metadata={
                "memory_kind": "semantic",
                "memory_user_id": "user-1",
                "memory_created_at": _CREATED.isoformat(),
                "memory_expires_at": correction_expiry.isoformat(),
                "memory_supersedes": original.id,
            },
        ),
        RetrievalHit(
            id=independent.id,
            content=independent.content,
            source=independent.source,
            content_digest=independent.content_digest,
            revision=independent.revision,
            tenant_id="tenant-1",
            namespace="support",
            metadata={
                "memory_kind": "user",
                "memory_user_id": "user-1",
                "memory_created_at": _CREATED.isoformat(),
                "memory_expires_at": None,
                "memory_supersedes": None,
            },
        ),
    )
    assert store.search_calls == [
        (
            "remembered preference",
            5,
            "tenant-1",
            "user-1",
            "support",
            tuple(MemoryKind),
            {
                "nested": {"value": 1},
                "values": (None, "text", True, 1.5),
            },
        )
    ]


@pytest.mark.parametrize(
    ("query", "limit", "tenant_id", "namespace"),
    [
        (" ", 1, "tenant-1", "support"),
        # Runtime-boundary probes intentionally violate static annotations.
        (cast(str, 1), 1, "tenant-1", "support"),
        ("query", cast(int, True), "tenant-1", "support"),
        ("query", cast(int, 1.5), "tenant-1", "support"),
        ("query", 0, "tenant-1", "support"),
        ("query", 1, None, "support"),
        ("query", 1, "tenant-1", None),
    ],
)
async def test_memory_retriever_invalid_request_expect_agent_memory_error(
    query: str,
    limit: int,
    tenant_id: str | None,
    namespace: str | None,
) -> None:
    """Query, limit, and both inherited retrieval scopes remain fail-closed."""
    with pytest.raises(AgentMemoryError):
        await _retriever(FakeMemoryStore()).retrieve(
            query,
            limit=limit,
            tenant_id=tenant_id,
            namespace=namespace,
            filters={},
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: MemoryRetriever(
            cast(IMemoryStore, object()),
            tenant_id="tenant-1",
            user_id="user-1",
            namespace="support",
        ),
        lambda: MemoryRetriever(
            FakeMemoryStore(),
            tenant_id=" ",
            user_id="user-1",
            namespace="support",
        ),
        lambda: _retriever(FakeMemoryStore(), kinds=()),
        lambda: _retriever(
            FakeMemoryStore(),
            kinds=cast(tuple[MemoryKind, ...], [MemoryKind.USER]),
        ),
        lambda: _retriever(
            FakeMemoryStore(),
            kinds=(cast(MemoryKind, "invalid"),),
        ),
        lambda: _retriever(
            FakeMemoryStore(),
            kinds=(MemoryKind.USER, MemoryKind.USER),
        ),
    ],
)
def test_memory_retriever_invalid_binding_expect_agent_definition_error(
    factory: Callable[[], MemoryRetriever],
) -> None:
    """A retriever cannot bootstrap without one exact store, scope, and kind set."""
    with pytest.raises(AgentDefinitionError):
        factory()


@pytest.mark.parametrize(
    "entries",
    [
        object(),
        "invalid",
        ("invalid",),
        (_entry(), _entry()),
        (replace(_entry(), tenant_id="other"),),
        (replace(_entry(), user_id="other"),),
        (replace(_entry(), namespace="other"),),
        (_entry(kind=MemoryKind.EPISODIC),),
        (
            _entry("correction-1", supersedes="original"),
            _entry("correction-2", supersedes="original"),
        ),
    ],
)
async def test_memory_retriever_malformed_store_result_expect_agent_memory_error(
    entries: object,
) -> None:
    """A backend cannot inject malformed, duplicate, cross-scope, or conflicting data."""
    store = FakeMemoryStore()
    store.result_override = entries
    retriever = _retriever(store, kinds=(MemoryKind.SEMANTIC,))

    with pytest.raises(AgentMemoryError):
        await retriever.retrieve(
            "query",
            limit=2,
            tenant_id="tenant-1",
            namespace="support",
            filters={},
        )


async def test_memory_retriever_active_correction_cycle_expect_agent_memory_error() -> (
    None
):
    """A correction cycle cannot silently remove every involved memory."""
    retriever = _retriever(
        FakeMemoryStore(
            (
                _entry("memory-a", supersedes="memory-b"),
                _entry("memory-b", supersedes="memory-a"),
            )
        )
    )

    with pytest.raises(AgentMemoryError, match="cycle"):
        await retriever.retrieve(
            "query",
            limit=2,
            tenant_id="tenant-1",
            namespace="support",
            filters={},
        )


@pytest.mark.parametrize(
    "filters",
    [
        cast(JsonObject, []),
        cast(JsonObject, {1: "invalid"}),
        {"value": inf},
        {"value": object()},
        {"value": bytearray(b"invalid")},
    ],
)
async def test_memory_retriever_invalid_filters_expect_agent_memory_error(
    filters: JsonObject,
) -> None:
    """Only deeply copied finite JSON filters cross into the memory store."""
    with pytest.raises(AgentMemoryError):
        await _retriever(FakeMemoryStore()).retrieve(
            "query",
            limit=1,
            tenant_id="tenant-1",
            namespace="support",
            filters=filters,
        )
