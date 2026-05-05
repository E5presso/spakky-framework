"""Typed context contracts for agent model input assembly."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from spakky.agent.types import JsonObject, JsonValue


class ContextPackRole(StrEnum):
    """Semantic role of a context pack inside a model request."""

    SYSTEM = "system"
    INSTRUCTION = "instruction"
    TASK = "task"
    STATE = "state"
    EVIDENCE = "evidence"
    TOOL_RESULT = "tool_result"
    DELEGATION = "delegation"
    MEMORY = "memory"


class ContextFreshness(StrEnum):
    """Freshness classification for context rot and budget decisions."""

    CURRENT = "current"
    RECENT = "recent"
    STALE = "stale"
    UNKNOWN = "unknown"


class ContextSensitivity(StrEnum):
    """Deterministic sensitivity metadata carried before model input."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SENSITIVE = "sensitive"
    REDACTED = "redacted"


@dataclass(frozen=True, slots=True)
class ContextTokenBudget:
    """Token budget allocated to one context pack."""

    max_tokens: int | None = None
    estimated_tokens: int | None = None
    reserved_output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ContextPack:
    """LLM-facing context unit derived from state, signal, or evidence."""

    id: str
    content: str
    source: str
    role: ContextPackRole
    freshness: ContextFreshness = ContextFreshness.UNKNOWN
    relevance: float | None = None
    token_budget: ContextTokenBudget = field(default_factory=ContextTokenBudget)
    sensitivity: ContextSensitivity = ContextSensitivity.INTERNAL
    metadata: JsonObject = field(default_factory=dict)

    def message_metadata(self) -> Mapping[str, JsonValue]:
        """Return non-content metadata for provider-neutral model messages."""
        return {
            "context_pack_id": self.id,
            "source": self.source,
            "role": self.role.value,
            "freshness": self.freshness.value,
            "relevance": self.relevance,
            "token_budget": {
                "max_tokens": self.token_budget.max_tokens,
                "estimated_tokens": self.token_budget.estimated_tokens,
                "reserved_output_tokens": self.token_budget.reserved_output_tokens,
            },
            "sensitivity": self.sensitivity.value,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class ContextManifestEntry:
    """One audited pack entry inside a context manifest."""

    pack_id: str
    source: str
    role: ContextPackRole
    origin_ref: str
    evidence_ref: str | None = None
    digest_ref: str | None = None
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextManifest:
    """Auditable composition record for model input context packs."""

    id: str
    entries: Sequence[ContextManifestEntry]
    origin_ref: str | None = None
    evidence_refs: Sequence[str] = field(default_factory=tuple)
    created_at: datetime | None = None
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextDigest:
    """Derived compression evidence for a context identity."""

    id: str
    context_identity: str
    source_manifest_ref: str
    digest: str
    derived_from_pack_ids: Sequence[str] = field(default_factory=tuple)
    compression_evidence_ref: str | None = None
    algorithm: str | None = None
    summary: str | None = None
    created_at: datetime | None = None
    metadata: JsonObject = field(default_factory=dict)
