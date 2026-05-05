"""Tests for agent context health and optimization contracts."""

from collections.abc import Sequence

from spakky.agent import (
    AgentEvidenceCandidate,
    AgentEvidenceKind,
    AgentYield,
    AgentYieldKind,
    ContextHealthSignal,
    ContextManifest,
    ContextOptimizationAction,
    ContextOptimizationActionKind,
    ContextOptimizationEvidenceStage,
    ContextRotSymptom,
    Evidence,
    IAgentContextHandler,
)


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
