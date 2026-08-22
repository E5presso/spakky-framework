"""Tests for agent context health and optimization contracts."""

from collections.abc import Sequence
from math import nan

import pytest

from spakky.agent import (
    AgentContext,
    AgentDefinitionError,
    AgentEvidenceCandidate,
    AgentEvidenceKind,
    AgentYield,
    AgentYieldKind,
    ContextHealthSignal,
    ContextDigest,
    ContextFreshness,
    ContextManifest,
    ContextManifestEntry,
    ContextOptimizationAction,
    ContextOptimizationActionKind,
    ContextOptimizationEvidenceStage,
    ContextRotSymptom,
    ContextPack,
    ContextPackRole,
    ContextSensitivity,
    ContextTokenBudget,
    Evidence,
    IAgentContextHandler,
    JsonValue,
)
from spakky.agent.context import combine_agent_contexts, prepare_agent_context


class _ContextHandlerDouble(IAgentContextHandler):
    def select_optimization_actions(
        self,
        signals: Sequence[ContextHealthSignal],
        manifest: ContextManifest,
    ) -> Sequence[ContextOptimizationAction]:
        over_budget_refs = tuple(
            signal.id
            for signal in signals
            if signal.symptom == ContextRotSymptom.OVER_BUDGET
        )
        return (
            ContextOptimizationAction(
                id="ctx-action-1",
                kind=ContextOptimizationActionKind.COMPRESSION,
                signal_refs=over_budget_refs,
                target_pack_ids=("pack-1", "pack-2"),
                manifest_ref=manifest.id,
                digest_ref="digest-1",
                reason="summarize older evidence packs",
            ),
        )


def test_context_rot_signal_expect_covers_required_symptoms() -> None:
    """FR-023 context rot symptom vocabulary를 typed enum으로 표현한다."""
    symptoms = {symptom.value for symptom in ContextRotSymptom}

    assert symptoms == {
        "stale",
        "contradictory",
        "low_relevance",
        "over_budget",
        "polluted",
    }


def test_context_optimization_action_expect_covers_required_actions() -> None:
    """압축, retrieval refresh, delegation, slice drop action을 열거한다."""
    actions = {action.value for action in ContextOptimizationActionKind}

    assert actions == {
        "compression",
        "retrieval_refresh",
        "delegation",
        "context_slice_drop",
    }


def test_context_handler_expect_selects_actions_without_raw_evidence_mutation() -> None:
    """handler hook은 signal과 manifest에서 action metadata만 선택한다."""
    handler: IAgentContextHandler = _ContextHandlerDouble()
    manifest = ContextManifest(id="manifest-1", entries=())
    signals = (
        ContextHealthSignal(
            id="signal-1",
            symptom=ContextRotSymptom.OVER_BUDGET,
            manifest_ref="manifest-1",
            pack_id="pack-1",
            score=0.91,
        ),
    )

    actions = handler.select_optimization_actions(signals, manifest)

    assert len(actions) == 1
    assert actions[0].kind == ContextOptimizationActionKind.COMPRESSION
    assert actions[0].signal_refs == ("signal-1",)
    assert actions[0].target_pack_ids == ("pack-1", "pack-2")
    assert actions[0].manifest_ref == "manifest-1"
    assert "raw" not in actions[0].evidence_payload()


def test_context_optimization_expect_creates_before_after_evidence() -> None:
    """optimization action은 실행 전후 append-only evidence/yield로 남길 수 있다."""
    signal = ContextHealthSignal(
        id="signal-1",
        symptom=ContextRotSymptom.LOW_RELEVANCE,
        manifest_ref="manifest-1",
        pack_id="pack-old",
        evidence_ref="evidence-raw-1",
        metadata={"reason": "obsolete tool output"},
    )
    action = ContextOptimizationAction(
        id="ctx-action-1",
        kind=ContextOptimizationActionKind.CONTEXT_SLICE_DROP,
        signal_refs=(signal.id,),
        target_pack_ids=("pack-old",),
        manifest_ref="manifest-1",
        result_evidence_ref="evidence-derived-1",
        reason="drop obsolete context slice from next model call",
    )

    before = AgentEvidenceCandidate.context_optimization(
        action=action,
        stage=ContextOptimizationEvidenceStage.BEFORE,
        signals=(signal,),
        summary="planned context slice drop",
    )
    after = AgentEvidenceCandidate.context_optimization(
        action=action,
        stage=ContextOptimizationEvidenceStage.AFTER,
        signals=(signal,),
        summary="applied context slice drop",
    )
    evidence = after.to_evidence(
        evidence_id="evidence-derived-1",
        agent_state_id="run-1",
    )
    yielded = AgentYield(kind=AgentYieldKind.EVIDENCE, payload=Evidence(evidence))

    assert before.kind == AgentEvidenceKind.CONTEXT_OPTIMIZATION
    assert before.payload["stage"] == "before"
    assert after.payload["stage"] == "after"
    assert after.payload["action"] == {
        "id": "ctx-action-1",
        "kind": "context_slice_drop",
        "signal_refs": ("signal-1",),
        "target_pack_ids": ("pack-old",),
        "manifest_ref": "manifest-1",
        "digest_ref": None,
        "delegation_ref": None,
        "result_evidence_ref": "evidence-derived-1",
        "reason": "drop obsolete context slice from next model call",
        "metadata": {},
    }
    assert evidence.kind == AgentEvidenceKind.CONTEXT_OPTIMIZATION
    assert evidence.reference == "evidence-derived-1"
    assert yielded.payload.evidence is evidence


def test_agent_context_combines_static_dynamic_order_and_synthesizes_manifest() -> None:
    """Static packs precede dynamic packs under one deterministic exact manifest."""
    static = ContextPack("static", "s", "input", ContextPackRole.TASK)
    dynamic = ContextPack("dynamic", "d", "provider", ContextPackRole.STATE)

    combined = combine_agent_contexts(
        AgentContext(packs=(static,)),
        AgentContext(packs=(dynamic,)),
    )

    assert combined.packs == (static, dynamic)
    assert combined.manifest is not None
    assert [entry.pack_id for entry in combined.manifest.entries] == [
        "static",
        "dynamic",
    ]
    assert (
        combine_agent_contexts(
            AgentContext(packs=(static,)),
            AgentContext(packs=(dynamic,)),
        ).manifest
        == combined.manifest
    )


def test_agent_context_composes_independent_manifests_but_rejects_partial_digest() -> (
    None
):
    """Envelope provenance composes; a subset digest is never promoted globally."""
    static = ContextPack("static", "s", "input", ContextPackRole.TASK)
    dynamic = ContextPack("dynamic", "d", "provider", ContextPackRole.STATE)
    static_manifest = ContextManifest(
        "static-manifest",
        (
            ContextManifestEntry(
                "static", "input", ContextPackRole.TASK, "static-origin"
            ),
        ),
        evidence_refs=("evidence-static",),
    )
    dynamic_manifest = ContextManifest(
        "dynamic-manifest",
        (
            ContextManifestEntry(
                "dynamic", "provider", ContextPackRole.STATE, "dynamic-origin"
            ),
        ),
        evidence_refs=("evidence-dynamic",),
    )

    combined = combine_agent_contexts(
        AgentContext(packs=(static,), manifest=static_manifest),
        AgentContext(packs=(dynamic,), manifest=dynamic_manifest),
    )

    assert combined.manifest is not None
    assert [entry.origin_ref for entry in combined.manifest.entries] == [
        "static-origin",
        "dynamic-origin",
    ]
    assert tuple(combined.manifest.evidence_refs) == (
        "evidence-static",
        "evidence-dynamic",
    )
    assert combined.manifest.metadata["component_manifest_refs"] == (
        "static-manifest",
        "dynamic-manifest",
    )
    prepared = prepare_agent_context(combined)
    assert prepared.manifest is not None
    assert prepared.manifest.metadata == {
        "component_manifest_refs": ("static-manifest", "dynamic-manifest")
    }
    partial_digest = ContextDigest(
        "static-digest",
        "static-context",
        static_manifest.id,
        "sha256:static",
        ("static",),
    )
    with pytest.raises(AgentDefinitionError):
        combine_agent_contexts(
            AgentContext(
                packs=(static,),
                manifest=static_manifest,
                digest=partial_digest,
            ),
            AgentContext(packs=(dynamic,), manifest=dynamic_manifest),
        )


def test_agent_context_rejects_duplicate_and_incomplete_provenance() -> None:
    """Duplicate ids and partial/conflicting manifest or digest refs fail closed."""
    pack = ContextPack("pack-1", "content", "source", ContextPackRole.EVIDENCE)
    with pytest.raises(AgentDefinitionError):
        combine_agent_contexts(
            AgentContext(packs=(pack,)),
            AgentContext(packs=(pack,)),
        )
    with pytest.raises(AgentDefinitionError):
        combine_agent_contexts(AgentContext(packs=(pack, pack)), None)
    incomplete = ContextManifest(id="manifest", entries=())
    with pytest.raises(AgentDefinitionError):
        combine_agent_contexts(AgentContext(packs=(pack,), manifest=incomplete), None)
    with pytest.raises(AgentDefinitionError):
        combine_agent_contexts(AgentContext(manifest=incomplete), None)
    manifest = ContextManifest(
        id="manifest",
        entries=(
            ContextManifestEntry(
                pack_id="pack-1",
                source="source",
                role=ContextPackRole.EVIDENCE,
                origin_ref="source",
            ),
        ),
    )
    bad_digest = ContextDigest(
        id="digest",
        context_identity="run",
        source_manifest_ref="other",
        digest="sha256:value",
        derived_from_pack_ids=("pack-1",),
    )
    with pytest.raises(AgentDefinitionError):
        combine_agent_contexts(
            AgentContext(packs=(pack,), manifest=manifest, digest=bad_digest),
            None,
        )
    other_digest = ContextDigest(
        id="other-digest",
        context_identity="run",
        source_manifest_ref="manifest",
        digest="sha256:other",
        derived_from_pack_ids=("pack-1",),
    )
    with pytest.raises(AgentDefinitionError):
        combine_agent_contexts(
            AgentContext(packs=(pack,), manifest=manifest, digest=bad_digest),
            AgentContext(digest=other_digest),
        )
    with pytest.raises(AgentDefinitionError):
        combine_agent_contexts(AgentContext(digest=bad_digest), None)


def test_agent_context_preserves_valid_manifest_and_digest_provenance() -> None:
    """Caller-supplied exact manifest/digest survive validation unchanged."""
    pack = ContextPack("pack-1", "content", "source", ContextPackRole.EVIDENCE)
    manifest = ContextManifest(
        id="manifest",
        entries=(
            ContextManifestEntry(
                pack_id="pack-1",
                source="source",
                role=ContextPackRole.EVIDENCE,
                origin_ref="source",
            ),
        ),
    )
    digest = ContextDigest(
        id="digest",
        context_identity="run",
        source_manifest_ref="manifest",
        digest="sha256:value",
        derived_from_pack_ids=("pack-1",),
    )

    combined = combine_agent_contexts(
        AgentContext(packs=(pack,), manifest=manifest, digest=digest),
        None,
    )

    assert combined.manifest is manifest
    assert combined.digest is digest
    wrong_pack_digest = ContextDigest(
        id="wrong-pack",
        context_identity="run",
        source_manifest_ref="manifest",
        digest="sha256:wrong",
        derived_from_pack_ids=("other",),
    )
    with pytest.raises(AgentDefinitionError):
        combine_agent_contexts(
            AgentContext(
                packs=(pack,),
                manifest=manifest,
                digest=wrong_pack_digest,
            ),
            None,
        )
    conflicting_manifest = ContextManifest(
        id="manifest-conflict",
        entries=(
            ContextManifestEntry(
                pack_id="pack-1",
                source="other-source",
                role=ContextPackRole.STATE,
                origin_ref="other",
            ),
        ),
    )
    with pytest.raises(AgentDefinitionError):
        combine_agent_contexts(
            AgentContext(packs=(pack,), manifest=conflicting_manifest),
            None,
        )


def test_agent_context_budget_redacts_and_uses_explicit_estimate() -> None:
    """Redacted content stays fixed; explicit over-budget estimate truncates proportionally."""
    original = ContextPack(
        id="budgeted",
        content="x" * 100,
        source="source",
        role=ContextPackRole.EVIDENCE,
        freshness=ContextFreshness.CURRENT,
        token_budget=ContextTokenBudget(
            max_tokens=10,
            estimated_tokens=100,
            reserved_output_tokens=0,
        ),
    )
    redacted = ContextPack(
        id="redacted",
        content="secret",
        source="source",
        role=ContextPackRole.EVIDENCE,
        sensitivity=ContextSensitivity.REDACTED,
        token_budget=ContextTokenBudget(max_tokens=1, estimated_tokens=0),
    )

    prepared = prepare_agent_context(AgentContext(packs=(original, redacted)))

    assert len(prepared.packs[0].content) == 10
    assert prepared.packs[0].metadata["context_truncation"] == {
        "truncated": True,
        "original_characters": 100,
        "retained_characters": 10,
        "estimated_tokens": 100,
        "max_tokens": 10,
    }
    assert prepared.packs[1].content == "[REDACTED]"
    assert original.content == "x" * 100


@pytest.mark.parametrize(
    "budget",
    [
        ContextTokenBudget(max_tokens=1, estimated_tokens=0, reserved_output_tokens=0),
    ],
)
def test_context_budget_accepts_nonnegative_estimates_and_reservations(
    budget: ContextTokenBudget,
) -> None:
    assert budget.estimated_tokens == 0
    assert budget.reserved_output_tokens == 0


@pytest.mark.parametrize(
    "values",
    [
        {"max_tokens": 0},
        {"estimated_tokens": -1},
        {"reserved_output_tokens": -1},
    ],
)
def test_context_budget_rejects_invalid_limits(values: dict[str, int]) -> None:
    with pytest.raises(AgentDefinitionError):
        ContextTokenBudget(**values)


def test_context_pack_rejects_blank_required_identifier() -> None:
    with pytest.raises(AgentDefinitionError):
        ContextPack(" ", "content", "source", ContextPackRole.EVIDENCE)


def test_context_fingerprint_rejects_nonfinite_model_bound_metadata() -> None:
    pack = ContextPack(
        "pack",
        "content",
        "source",
        ContextPackRole.EVIDENCE,
        relevance=nan,
    )
    with pytest.raises(AgentDefinitionError, match="identity is not deterministic"):
        combine_agent_contexts(AgentContext(packs=(pack,)), None)


@pytest.mark.parametrize(
    "retrieval",
    [
        {"id": "hit", "unknown": "value"},
        {"id": " "},
        {"id": "hit\nframe"},
        {"id": "hit", "revision": "bad\rref"},
        {"id": "hit", "score": True},
        {"id": "hit", "score": nan},
        {"id": "hit", "start_offset": True, "end_offset": 2},
        {"id": "hit", "start_offset": -1, "end_offset": 2},
        {"id": "hit", "start_offset": 1},
        {"id": "hit", "start_offset": 2, "end_offset": 1},
    ],
)
def test_context_prepare_drops_spoofed_reserved_retrieval_metadata(
    retrieval: dict[str, JsonValue],
) -> None:
    pack = ContextPack(
        "pack",
        "content",
        "source",
        ContextPackRole.EVIDENCE,
        metadata={"retrieval": retrieval},
    )
    prepared = prepare_agent_context(AgentContext(packs=(pack,)))
    assert prepared.packs[0].metadata == {}
