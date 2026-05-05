"""Typed context contracts for agent model input assembly."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import cast

from spakky.agent.safety import (
    ContextExposurePolicy,
    SensitiveFieldDescriptor,
    guard_json_value,
)
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


class ContextRotSymptom(StrEnum):
    """Typed context rot symptoms observed before model input assembly."""

    STALE = "stale"
    CONTRADICTORY = "contradictory"
    LOW_RELEVANCE = "low_relevance"
    OVER_BUDGET = "over_budget"
    POLLUTED = "polluted"


class ContextOptimizationActionKind(StrEnum):
    """Optimization actions that can be selected from context health signals."""

    COMPRESSION = "compression"
    RETRIEVAL_REFRESH = "retrieval_refresh"
    DELEGATION = "delegation"
    CONTEXT_SLICE_DROP = "context_slice_drop"


class ContextOptimizationEvidenceStage(StrEnum):
    """Where an optimization action evidence item sits in the agent flow."""

    BEFORE = "before"
    AFTER = "after"


@dataclass(frozen=True, slots=True)
class ContextTokenBudget:
    """Token budget allocated to one context pack."""

    max_tokens: int | None = None
    estimated_tokens: int | None = None
    reserved_output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ContextHealthSignal:
    """Observed context rot signal used to choose optimization actions."""

    id: str
    symptom: ContextRotSymptom
    manifest_ref: str | None = None
    pack_id: str | None = None
    evidence_ref: str | None = None
    score: float | None = None
    observed_at: datetime | None = None
    metadata: JsonObject = field(default_factory=dict)

    def evidence_payload(self) -> Mapping[str, JsonValue]:
        """Return JSON-compatible signal metadata for append-only evidence."""
        return {
            "id": self.id,
            "symptom": self.symptom.value,
            "manifest_ref": self.manifest_ref,
            "pack_id": self.pack_id,
            "evidence_ref": self.evidence_ref,
            "score": self.score,
            "observed_at": self.observed_at.isoformat()
            if self.observed_at is not None
            else None,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class ContextOptimizationAction:
    """Selected optimization action derived from context health signals."""

    id: str
    kind: ContextOptimizationActionKind
    signal_refs: Sequence[str] = field(default_factory=tuple)
    target_pack_ids: Sequence[str] = field(default_factory=tuple)
    manifest_ref: str | None = None
    digest_ref: str | None = None
    delegation_ref: str | None = None
    result_evidence_ref: str | None = None
    reason: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    def evidence_payload(self) -> Mapping[str, JsonValue]:
        """Return JSON-compatible action metadata without raw context contents."""
        return {
            "id": self.id,
            "kind": self.kind.value,
            "signal_refs": tuple(self.signal_refs),
            "target_pack_ids": tuple(self.target_pack_ids),
            "manifest_ref": self.manifest_ref,
            "digest_ref": self.digest_ref,
            "delegation_ref": self.delegation_ref,
            "result_evidence_ref": self.result_evidence_ref,
            "reason": self.reason,
            "metadata": self.metadata,
        }


class IAgentContextHandler(ABC):
    """Select context optimization actions from health signals and manifests."""

    @abstractmethod
    def select_optimization_actions(
        self,
        signals: Sequence[ContextHealthSignal],
        manifest: "ContextManifest",
    ) -> Sequence[ContextOptimizationAction]:
        """Return optimization actions without mutating raw evidence."""
        ...


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
    sensitive_fields: tuple[SensitiveFieldDescriptor, ...] = ()
    metadata: JsonObject = field(default_factory=dict)

    def guarded_content(
        self,
        policy: ContextExposurePolicy | None = None,
    ) -> str:
        """Return deterministic model-safe content for this context pack."""
        exposure_policy = policy or ContextExposurePolicy()
        if self.sensitivity == ContextSensitivity.REDACTED:
            return "[REDACTED]"
        guarded = guard_json_value(
            {"content": self.content},
            tuple(
                SensitiveFieldDescriptor(
                    ("content", *descriptor.path), descriptor.field
                )
                for descriptor in self.sensitive_fields
            ),
            exposure_policy,
        )
        content = cast(Mapping[str, JsonValue], guarded).get("content")
        if isinstance(content, str):
            return content
        return "[REDACTED]"

    def message_metadata(
        self,
        policy: ContextExposurePolicy | None = None,
    ) -> Mapping[str, JsonValue]:
        """Return non-content metadata for provider-neutral model messages."""
        exposure_policy = policy or ContextExposurePolicy()
        metadata: dict[str, JsonValue] = {
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
        if exposure_policy.include_sensitive_context_metadata and self.sensitive_fields:
            metadata["sensitive_fields"] = tuple(
                descriptor.to_metadata() for descriptor in self.sensitive_fields
            )
        return metadata


@dataclass(frozen=True, slots=True)
class ContextManifestEntry:
    """One audited pack entry inside a context manifest."""

    pack_id: str
    source: str
    role: ContextPackRole
    origin_ref: str
    evidence_ref: str | None = None
    digest_ref: str | None = None
    sensitive_fields: tuple[SensitiveFieldDescriptor, ...] = ()
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
