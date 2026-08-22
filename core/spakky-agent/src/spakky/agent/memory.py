"""Typed, scoped long-term memory contracts over the retrieval boundary."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from math import isfinite
from typing import override

from spakky.agent.error import AgentDefinitionError, AgentMemoryError
from spakky.agent.retrieval import IRetriever, RetrievalHit
from spakky.agent.types import JsonObject, JsonValue


class MemoryKind(StrEnum):
    """Long-term memory meanings exposed independently from storage backends."""

    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    USER = "user"


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    """One immutable, provenance-bound long-term memory revision."""

    id: str
    kind: MemoryKind
    content: str
    source: str
    revision: str
    content_digest: str
    tenant_id: str
    user_id: str
    namespace: str
    created_at: datetime
    expires_at: datetime | None = None
    supersedes: str | None = None

    def __post_init__(self) -> None:
        """Reject entries that cannot be safely scoped or versioned."""
        for value, label in (
            (self.id, "Memory entry id must be nonblank single-line text"),
            (self.source, "Memory source must be nonblank single-line text"),
            (self.revision, "Memory revision must be nonblank single-line text"),
            (
                self.content_digest,
                "Memory content digest must be nonblank single-line text",
            ),
            (self.tenant_id, "Memory tenant id must be nonblank single-line text"),
            (self.user_id, "Memory user id must be nonblank single-line text"),
            (self.namespace, "Memory namespace must be nonblank single-line text"),
        ):
            _MemoryValidation.definition_text(value, label)
        if not isinstance(self.kind, MemoryKind):
            raise AgentDefinitionError("Memory kind is invalid")
        if not isinstance(self.content, str) or not self.content.strip():
            raise AgentDefinitionError("Memory content cannot be blank")
        _MemoryValidation.definition_timestamp(
            self.created_at,
            "Memory created time must be timezone-aware",
        )
        if self.expires_at is not None:
            _MemoryValidation.definition_timestamp(
                self.expires_at,
                "Memory expiry time must be timezone-aware",
            )
            if self.expires_at <= self.created_at:
                raise AgentDefinitionError(
                    "Memory expiry time must be after its created time"
                )
        if self.supersedes is not None:
            _MemoryValidation.definition_text(
                self.supersedes,
                "Superseded memory id must be nonblank single-line text",
            )
            if self.supersedes == self.id:
                raise AgentDefinitionError("Memory cannot supersede itself")

    @property
    def ttl(self) -> timedelta | None:
        """Return the declared lifetime, or ``None`` for non-expiring memory."""
        if self.expires_at is None:
            return None
        return self.expires_at - self.created_at

    def is_expired(self, at: datetime | None = None) -> bool:
        """Check expiry at a deterministic point, defaulting to current UTC time."""
        point = datetime.now(UTC) if at is None else at
        _MemoryValidation.runtime_timestamp(
            point,
            "Memory expiry check time must be timezone-aware",
        )
        return self.expires_at is not None and self.expires_at <= point


class IMemoryStore(ABC):
    """Backend-replaceable long-term memory persistence port.

    Implementations must omit explicitly deleted entries from ``search``.
    ``MemoryRetriever`` additionally removes expired and superseded revisions.
    """

    @abstractmethod
    async def save(self, entry: MemoryEntry) -> None:
        """Persist one immutable revision, including correction linkage."""
        ...

    @abstractmethod
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
        """Return ordered, undeleted candidates for one exact scope."""
        ...

    @abstractmethod
    async def delete(
        self,
        entry_id: str,
        *,
        tenant_id: str,
        user_id: str,
        namespace: str,
    ) -> None:
        """Explicitly delete one memory entry inside its exact scope."""
        ...


class MemoryRetriever(IRetriever):
    """Bind the missing user dimension before exposing memory as retrieval."""

    def __init__(
        self,
        store: IMemoryStore,
        *,
        tenant_id: str,
        user_id: str,
        namespace: str,
        kinds: tuple[MemoryKind, ...] = tuple(MemoryKind),
    ) -> None:
        if not isinstance(store, IMemoryStore):
            raise AgentDefinitionError("Memory retriever requires an IMemoryStore")
        for value, label in (
            (tenant_id, "Memory tenant id must be nonblank single-line text"),
            (user_id, "Memory user id must be nonblank single-line text"),
            (namespace, "Memory namespace must be nonblank single-line text"),
        ):
            _MemoryValidation.definition_text(value, label)
        if not isinstance(kinds, tuple) or not kinds:
            raise AgentDefinitionError("Memory retriever kinds cannot be empty")
        if any(not isinstance(kind, MemoryKind) for kind in kinds):
            raise AgentDefinitionError("Memory retriever kind is invalid")
        if len(set(kinds)) != len(kinds):
            raise AgentDefinitionError("Memory retriever kinds must be unique")
        self._store = store
        self._tenant_id = tenant_id
        self._user_id = user_id
        self._namespace = namespace
        self._kinds = kinds

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
        """Retrieve active memory without weakening its bound user scope."""
        if not isinstance(query, str) or not query.strip():
            raise AgentMemoryError("Memory retrieval query must be nonblank text")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise AgentMemoryError("Memory retrieval limit must be positive")
        if tenant_id != self._tenant_id or namespace != self._namespace:
            raise AgentMemoryError("Memory retrieval scope does not match its binding")
        copied_filters = _MemoryValidation.json_object(filters)
        entries = await self._store.search(
            query,
            limit=limit,
            tenant_id=self._tenant_id,
            user_id=self._user_id,
            namespace=self._namespace,
            kinds=self._kinds,
            filters=copied_filters,
        )
        return self._active_hits(entries, limit=limit, at=datetime.now(UTC))

    def _active_hits(
        self,
        entries: object,
        *,
        limit: int,
        at: datetime,
    ) -> tuple[RetrievalHit, ...]:
        """Validate an untrusted backend result before mapping active revisions."""
        if not isinstance(entries, Sequence) or isinstance(entries, str | bytes):
            raise AgentMemoryError("Memory store search result must be a sequence")
        active: list[MemoryEntry] = []
        seen: set[str] = set()
        superseded_targets: set[str] = set()
        for entry in entries:
            if not isinstance(entry, MemoryEntry):
                raise AgentMemoryError("Memory store returned an invalid entry")
            if entry.id in seen:
                raise AgentMemoryError("Memory store returned duplicate entry ids")
            if (
                entry.tenant_id != self._tenant_id
                or entry.user_id != self._user_id
                or entry.namespace != self._namespace
            ):
                raise AgentMemoryError("Memory store returned a mismatched scope")
            if entry.kind not in self._kinds:
                raise AgentMemoryError("Memory store returned an unrequested kind")
            seen.add(entry.id)
            if entry.is_expired(at):
                continue
            if entry.supersedes is not None:
                if entry.supersedes in superseded_targets:
                    raise AgentMemoryError(
                        "Memory store returned conflicting corrections"
                    )
                superseded_targets.add(entry.supersedes)
            active.append(entry)
        self._reject_correction_cycles(active)
        return tuple(
            self._to_hit(entry)
            for entry in active
            if entry.id not in superseded_targets
        )[:limit]

    def _reject_correction_cycles(self, entries: Sequence[MemoryEntry]) -> None:
        """Reject active correction graphs that can hide every revision."""
        by_id = {entry.id: entry for entry in entries}
        for entry in entries:
            path: set[str] = set()
            current: MemoryEntry | None = entry
            while current is not None:
                if current.id in path:
                    raise AgentMemoryError("Memory corrections contain a cycle")
                path.add(current.id)
                current = (
                    None
                    if current.supersedes is None
                    else by_id.get(current.supersedes)
                )

    def _to_hit(self, entry: MemoryEntry) -> RetrievalHit:
        """Map a validated memory revision to retrieval provenance."""
        return RetrievalHit(
            id=entry.id,
            content=entry.content,
            source=entry.source,
            content_digest=entry.content_digest,
            revision=entry.revision,
            tenant_id=entry.tenant_id,
            namespace=entry.namespace,
            metadata={
                "memory_kind": entry.kind.value,
                "memory_user_id": entry.user_id,
                "memory_created_at": entry.created_at.isoformat(),
                "memory_expires_at": (
                    None if entry.expires_at is None else entry.expires_at.isoformat()
                ),
                "memory_supersedes": entry.supersedes,
            },
        )


class _MemoryValidation:
    """Centralize runtime validation without weakening public memory types."""

    @staticmethod
    def definition_text(value: object, message: str) -> None:
        """Validate definition-time single-line identifiers from runtime callers."""
        if (
            not isinstance(value, str)
            or not value.strip()
            or "\n" in value
            or "\r" in value
        ):
            raise AgentDefinitionError(message)

    @staticmethod
    def definition_timestamp(value: object, message: str) -> None:
        """Validate an aware definition-time timestamp."""
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise AgentDefinitionError(message)

    @staticmethod
    def runtime_timestamp(value: object, message: str) -> None:
        """Validate an aware timestamp crossing a runtime memory boundary."""
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise AgentMemoryError(message)

    @staticmethod
    def json_object(value: object) -> JsonObject:
        """Return an immutable-by-copy JSON object for the store boundary."""
        if not isinstance(value, Mapping):
            raise AgentMemoryError("Memory filters must be a JSON object")
        copied: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise AgentMemoryError("Memory filter keys must be text")
            copied[key] = _MemoryValidation.json_value(item)
        return copied

    @staticmethod
    def json_value(value: object) -> JsonValue:
        """Copy one untrusted recursive JSON filter value."""
        if value is None or isinstance(value, str | int | bool):
            return value
        if isinstance(value, float):
            if not isfinite(value):
                raise AgentMemoryError("Memory filters must contain finite numbers")
            return value
        if isinstance(value, Mapping):
            return _MemoryValidation.json_object(value)
        if isinstance(value, Sequence) and not isinstance(
            value,
            str | bytes | bytearray,
        ):
            return tuple(_MemoryValidation.json_value(item) for item in value)
        raise AgentMemoryError("Memory filters must contain JSON values")
