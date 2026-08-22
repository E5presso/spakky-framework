"""Typed context contracts for agent model input assembly."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from json import dumps
from math import isfinite
from typing import TYPE_CHECKING, cast

from spakky.agent.error import AgentDefinitionError
from spakky.agent.safety import (
    ContextExposurePolicy,
    SensitiveFieldDescriptor,
    guard_json_value,
)
from spakky.agent.types import JsonObject, JsonValue

if TYPE_CHECKING:  # pragma: no cover - static-only circular import
    from spakky.agent.inbound import RunAgentInput

_ESTIMATED_CHARACTERS_PER_TOKEN = 4
_SAFE_RETRIEVAL_METADATA_KEYS = frozenset(
    {
        "id",
        "score",
        "rerank_score",
        "content_digest",
        "revision",
        "tenant_id",
        "namespace",
        "start_offset",
        "end_offset",
    }
)


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

    def __post_init__(self) -> None:
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise AgentDefinitionError("Context max token budget must be positive")
        for value in (self.estimated_tokens, self.reserved_output_tokens):
            if value is not None and value < 0:
                raise AgentDefinitionError(
                    "Context estimated and reserved tokens must be nonnegative"
                )


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

    def __post_init__(self) -> None:
        _require_non_blank(self.id, "Context pack id")
        _require_non_blank(self.source, "Context pack source")

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

    def __post_init__(self) -> None:
        _require_non_blank(self.pack_id, "Context manifest pack id")
        _require_non_blank(self.source, "Context manifest source")
        _require_non_blank(self.origin_ref, "Context manifest origin ref")
        _require_optional_non_blank(self.evidence_ref, "Context manifest evidence ref")
        _require_optional_non_blank(self.digest_ref, "Context manifest digest ref")


@dataclass(frozen=True, slots=True)
class ContextManifest:
    """Auditable composition record for model input context packs."""

    id: str
    entries: Sequence[ContextManifestEntry]
    origin_ref: str | None = None
    evidence_refs: Sequence[str] = field(default_factory=tuple)
    created_at: datetime | None = None
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_blank(self.id, "Context manifest id")
        _require_optional_non_blank(self.origin_ref, "Context manifest origin ref")
        for evidence_ref in self.evidence_refs:
            _require_non_blank(evidence_ref, "Context manifest evidence ref")


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

    def __post_init__(self) -> None:
        _require_non_blank(self.id, "Context digest id")
        _require_non_blank(self.context_identity, "Context digest identity")
        _require_non_blank(self.source_manifest_ref, "Context digest manifest ref")
        _require_non_blank(self.digest, "Context digest value")
        for pack_id in self.derived_from_pack_ids:
            _require_non_blank(pack_id, "Context digest pack id")
        _require_optional_non_blank(
            self.compression_evidence_ref,
            "Context digest compression evidence ref",
        )
        _require_optional_non_blank(self.algorithm, "Context digest algorithm")


@dataclass(frozen=True, slots=True)
class AgentContext:
    """Typed context supplied statically or by one injected provider."""

    packs: tuple[ContextPack, ...] = ()
    manifest: ContextManifest | None = None
    digest: ContextDigest | None = None


class IAgentContextProvider(ABC):
    """Optional async port that supplies context for one model step."""

    @abstractmethod
    async def provide(
        self,
        run_input: "RunAgentInput",
        model_step: int,
    ) -> AgentContext:
        """Return context for the 1-based model step."""
        ...


def combine_agent_contexts(
    static: AgentContext,
    dynamic: AgentContext | None,
) -> AgentContext:
    """Combine static and dynamic context, validating exact provenance coverage."""
    contexts = (static,) if dynamic is None else (static, dynamic)
    envelopes = tuple(_validated_envelope(context) for context in contexts)
    packs = tuple(pack for context, _, _ in envelopes for pack in context.packs)
    pack_ids = tuple(pack.id for pack in packs)
    if len(set(pack_ids)) != len(pack_ids):
        raise AgentDefinitionError("Agent context pack ids must be unique")
    populated = tuple(envelope for envelope in envelopes if envelope[0].packs)
    if len(populated) == 0:
        manifest = None
        digest = None
    elif len(populated) == 1:
        _, manifest, digest = populated[0]
    else:
        if any(digest is not None for _, _, digest in populated):
            raise AgentDefinitionError(
                "Agent context cannot compose partial context digests"
            )
        component_manifests = tuple(
            manifest for _, manifest, _ in populated if manifest is not None
        )
        manifest = _composite_manifest(component_manifests, packs)
        digest = None
    return AgentContext(packs=packs, manifest=manifest, digest=digest)


def prepare_agent_context(context: AgentContext) -> AgentContext:
    """Return model-safe budgeted packs without mutating caller-owned context."""
    prepared = tuple(_prepare_pack(pack) for pack in context.packs)
    manifest = context.manifest
    if manifest is not None:
        component_refs = manifest.metadata.get("component_manifest_refs", ())
        safe_metadata: JsonObject = {}
        if (
            isinstance(component_refs, Sequence)
            and not isinstance(component_refs, str | bytes)
            and len(component_refs) > 0
            and all(isinstance(item, str) for item in component_refs)
        ):
            safe_metadata = {"component_manifest_refs": tuple(component_refs)}
        manifest = replace(
            manifest,
            entries=tuple(
                replace(entry, sensitive_fields=(), metadata={})
                for entry in manifest.entries
            ),
            metadata=safe_metadata,
        )
    digest = context.digest
    if digest is not None:
        digest = replace(digest, summary=None, metadata={})
    return AgentContext(packs=prepared, manifest=manifest, digest=digest)


def _agent_context_fingerprint(context: AgentContext) -> str | None:
    """Hash the exact privacy-safe context crossing the model boundary."""
    if not context.packs and context.manifest is None and context.digest is None:
        return None
    payload = {
        "packs": tuple(_pack_identity(pack) for pack in context.packs),
        "manifest": None
        if context.manifest is None
        else _manifest_identity(context.manifest),
        "digest": None if context.digest is None else _digest_identity(context.digest),
    }
    return _identity_digest(payload)


def _prepare_pack(pack: ContextPack) -> ContextPack:
    guarded = pack.guarded_content()
    safe_metadata = _safe_pack_metadata(pack.metadata)
    max_tokens = pack.token_budget.max_tokens
    if pack.sensitivity is ContextSensitivity.REDACTED or max_tokens is None:
        return replace(
            pack,
            content=guarded,
            sensitive_fields=(),
            metadata=safe_metadata,
        )
    max_characters = max_tokens * _ESTIMATED_CHARACTERS_PER_TOKEN
    estimated_tokens = pack.token_budget.estimated_tokens
    if estimated_tokens is not None and estimated_tokens > max_tokens:
        proportional_characters = (len(guarded) * max_tokens) // estimated_tokens
        max_characters = min(max_characters, proportional_characters)
    if len(guarded) <= max_characters:
        return replace(
            pack,
            content=guarded,
            sensitive_fields=(),
            metadata=safe_metadata,
        )
    return replace(
        pack,
        content=guarded[:max_characters],
        sensitive_fields=(),
        metadata={
            **safe_metadata,
            "context_truncation": {
                "truncated": True,
                "original_characters": len(guarded),
                "retained_characters": max_characters,
                "estimated_tokens": estimated_tokens,
                "max_tokens": max_tokens,
            },
        },
    )


def _safe_pack_metadata(metadata: JsonObject) -> JsonObject:
    retrieval = metadata.get("retrieval")
    if not isinstance(retrieval, Mapping):
        return {}
    if any(key not in _SAFE_RETRIEVAL_METADATA_KEYS for key in retrieval):
        return {}
    identifier = retrieval.get("id")
    if (
        not isinstance(identifier, str)
        or not identifier.strip()
        or "\n" in identifier
        or "\r" in identifier
    ):
        return {}
    for key in ("content_digest", "revision", "tenant_id", "namespace"):
        value = retrieval.get(key)
        if value is not None and (
            not isinstance(value, str)
            or not value.strip()
            or "\n" in value
            or "\r" in value
        ):
            return {}
    for key in ("score", "rerank_score"):
        value = retrieval.get(key)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not isfinite(value)
        ):
            return {}
    for key in ("start_offset", "end_offset"):
        value = retrieval.get(key)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            return {}
    start = retrieval.get("start_offset")
    end = retrieval.get("end_offset")
    if (start is None) != (end is None):
        return {}
    if isinstance(start, int) and isinstance(end, int) and end <= start:
        return {}
    return {"retrieval": dict(retrieval)}


def _validated_envelope(
    context: AgentContext,
) -> tuple[AgentContext, ContextManifest | None, ContextDigest | None]:
    pack_ids = tuple(pack.id for pack in context.packs)
    if len(set(pack_ids)) != len(pack_ids):
        raise AgentDefinitionError("Agent context pack ids must be unique")
    if not context.packs and (
        context.manifest is not None or context.digest is not None
    ):
        raise AgentDefinitionError(
            "Agent context provenance cannot exist without context packs"
        )
    manifest = context.manifest
    if manifest is None and context.packs:
        manifest = _synthesized_manifest(context.packs)
    if manifest is not None:
        _validate_manifest(manifest, context.packs)
    digest = context.digest
    if digest is not None:
        _validate_digest(digest, cast(ContextManifest, manifest), pack_ids)
    return context, manifest, digest


def _composite_manifest(
    manifests: tuple[ContextManifest, ...],
    packs: tuple[ContextPack, ...],
) -> ContextManifest:
    entries = tuple(entry for manifest in manifests for entry in manifest.entries)
    identity = _identity_digest(
        {
            "packs": tuple(_pack_identity(pack) for pack in packs),
            "components": tuple(_manifest_identity(manifest) for manifest in manifests),
        }
    )
    return ContextManifest(
        id=f"context-manifest:{identity}",
        entries=entries,
        origin_ref="agent-context-composite",
        evidence_refs=tuple(
            evidence_ref
            for manifest in manifests
            for evidence_ref in manifest.evidence_refs
        ),
        metadata={
            "component_manifest_refs": tuple(manifest.id for manifest in manifests)
        },
    )


def _synthesized_manifest(packs: tuple[ContextPack, ...]) -> ContextManifest:
    identity = _identity_digest(
        {"packs": tuple(_pack_identity(pack) for pack in packs)}
    )
    return ContextManifest(
        id=f"context-manifest:{identity}",
        entries=tuple(
            ContextManifestEntry(
                pack_id=pack.id,
                source=pack.source,
                role=pack.role,
                origin_ref=pack.source,
            )
            for pack in packs
        ),
        origin_ref="agent-context",
    )


def _pack_identity(pack: ContextPack) -> JsonObject:
    return {
        "id": pack.id,
        "content": pack.content,
        "source": pack.source,
        "role": pack.role.value,
        "sensitivity": pack.sensitivity.value,
        "freshness": pack.freshness.value,
        "relevance": pack.relevance,
        "budget": {
            "max_tokens": pack.token_budget.max_tokens,
            "estimated_tokens": pack.token_budget.estimated_tokens,
            "reserved_output_tokens": pack.token_budget.reserved_output_tokens,
        },
        "metadata": pack.metadata,
    }


def _manifest_identity(manifest: ContextManifest) -> JsonObject:
    return {
        "id": manifest.id,
        "origin_ref": manifest.origin_ref,
        "evidence_refs": tuple(manifest.evidence_refs),
        "component_manifest_refs": manifest.metadata.get(
            "component_manifest_refs",
            (),
        ),
        "entries": tuple(
            {
                "pack_id": entry.pack_id,
                "source": entry.source,
                "role": entry.role.value,
                "origin_ref": entry.origin_ref,
                "evidence_ref": entry.evidence_ref,
                "digest_ref": entry.digest_ref,
            }
            for entry in manifest.entries
        ),
    }


def _digest_identity(digest: ContextDigest) -> JsonObject:
    return {
        "id": digest.id,
        "context_identity": digest.context_identity,
        "source_manifest_ref": digest.source_manifest_ref,
        "digest": digest.digest,
        "derived_from_pack_ids": tuple(digest.derived_from_pack_ids),
        "compression_evidence_ref": digest.compression_evidence_ref,
        "algorithm": digest.algorithm,
    }


def _identity_digest(payload: JsonObject) -> str:
    try:
        encoded = dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError) as error:
        raise AgentDefinitionError(
            "Agent context identity is not deterministic"
        ) from error
    return sha256(encoded).hexdigest()


def _validate_manifest(
    manifest: ContextManifest,
    packs: tuple[ContextPack, ...],
) -> None:
    entries = tuple(manifest.entries)
    if len(entries) != len(packs):
        raise AgentDefinitionError("Agent context manifest coverage is incomplete")
    for entry, pack in zip(entries, packs, strict=True):
        if (
            entry.pack_id != pack.id
            or entry.source != pack.source
            or entry.role is not pack.role
        ):
            raise AgentDefinitionError("Agent context manifest provenance conflicts")


def _validate_digest(
    digest: ContextDigest,
    manifest: ContextManifest,
    pack_ids: tuple[str, ...],
) -> None:
    if digest.source_manifest_ref != manifest.id:
        raise AgentDefinitionError("Agent context digest manifest ref conflicts")
    if tuple(digest.derived_from_pack_ids) != pack_ids:
        raise AgentDefinitionError("Agent context digest pack coverage conflicts")


def _require_non_blank(value: str, label: str) -> None:
    if not value.strip():
        raise AgentDefinitionError(f"{label} cannot be blank")


def _require_optional_non_blank(value: str | None, label: str) -> None:
    if value is not None:
        _require_non_blank(value, label)
