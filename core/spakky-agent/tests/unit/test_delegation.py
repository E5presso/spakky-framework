"""Tests for agent delegation contracts."""

from collections.abc import AsyncGenerator

import pytest

from spakky.agent import (
    AgentDelegateTarget,
    AgentDefinitionError,
    AgentEvidenceKind,
    AgentYield,
    AgentYieldKind,
    DelegationBudget,
    DelegationContextSlice,
    DelegationExpectedOutput,
    DelegationPacket,
    DelegationResult,
    DelegationReturnPolicy,
    Evidence,
    IAgentDelegate,
)


def test_delegation_packet_expect_expresses_task_context_constraints_output_budget() -> (
    None
):
    """DelegationPacket이 delegation 최소 task packet을 표현한다."""
    packet = DelegationPacket(
        id="delegation-1",
        parent_agent_state_id="run-parent",
        target=AgentDelegateTarget(
            agent_type="ResearchAgent",
            agent_name="researcher",
        ),
        task={"goal": "summarize ADR-0009 delegation section"},
        context=DelegationContextSlice(
            summary="parent inspected the issue",
            evidence_refs=("evidence-1",),
            manifest_ref="manifest-1",
        ),
        constraints=("do not mutate workspace",),
        expected_output=DelegationExpectedOutput(
            description="short Korean summary",
            schema={"type": "object"},
        ),
        budget=DelegationBudget(max_steps=3, max_tokens=1200, timeout_seconds=30),
        allowed_capabilities=("read", "search"),
        return_policy=DelegationReturnPolicy.SUMMARY_AND_EVIDENCE,
    )

    assert packet.target.agent_type == "ResearchAgent"
    assert packet.task == {"goal": "summarize ADR-0009 delegation section"}
    assert packet.context.evidence_refs == ("evidence-1",)
    assert packet.constraints == ("do not mutate workspace",)
    assert packet.expected_output.schema == {"type": "object"}
    assert packet.budget.max_tokens == 1200
    assert packet.allowed_capabilities == ("read", "search")


def test_delegation_result_expect_links_parent_evidence_and_agent_yield() -> None:
    """Delegated result가 parent evidence와 AgentYield stream item으로 연결된다."""
    result = DelegationResult(
        id="delegation-result-1",
        packet_id="delegation-1",
        target=AgentDelegateTarget(agent_type="ResearchAgent"),
        summary="ADR section summarized",
        output={"answer": "delegation is a building block"},
        evidence_refs=("child-evidence-1",),
    )

    evidence = result.to_parent_evidence(
        evidence_id="parent-evidence-1",
        parent_agent_state_id="run-parent",
    )
    stream_item = result.to_parent_yield(
        evidence_id="parent-evidence-2",
        parent_agent_state_id="run-parent",
    )

    assert evidence.kind == AgentEvidenceKind.DELEGATION
    assert evidence.agent_state_id == "run-parent"
    assert evidence.payload["packet_id"] == "delegation-1"
    assert evidence.payload["target_agent_type"] == "ResearchAgent"
    assert evidence.payload["evidence_refs"] == ("child-evidence-1",)
    assert stream_item.kind == AgentYieldKind.EVIDENCE
    assert isinstance(stream_item.payload, Evidence)
    assert stream_item.payload.evidence.kind == AgentEvidenceKind.DELEGATION


def test_delegation_result_expect_preserves_named_target_without_output() -> None:
    """DelegationResult evidence가 named @Agent target을 output 없이도 연결한다."""
    result = DelegationResult(
        id="delegation-result-1",
        packet_id="delegation-1",
        target=AgentDelegateTarget(
            agent_type="ResearchAgent",
            agent_name="researcher",
        ),
        summary="child produced summary only",
    )

    evidence = result.to_parent_evidence(
        evidence_id="parent-evidence-1",
        parent_agent_state_id="run-parent",
    )

    assert evidence.payload["target_agent_name"] == "researcher"
    assert "output" not in evidence.payload


async def test_agent_delegate_hook_expect_streams_delegation_result_yields() -> None:
    """IAgentDelegate hook이 topology를 강제하지 않고 AgentYield stream을 반환한다."""
    packet = DelegationPacket(
        id="delegation-1",
        parent_agent_state_id="run-parent",
        target=AgentDelegateTarget(agent_type="ResearchAgent"),
        task={"goal": "inspect"},
    )
    delegate = RecordingDelegate()

    items = [item async for item in delegate.delegate(packet)]

    assert delegate.last_packet is packet
    assert len(items) == 1
    assert items[0].kind == AgentYieldKind.FINAL
    assert items[0].payload.packet_id == "delegation-1"


def test_delegation_contracts_expect_reject_blank_identity_and_invalid_budget() -> None:
    """Delegation 계약이 bootstrap 전에 불가능한 식별자와 budget을 거부한다."""
    with pytest.raises(AgentDefinitionError):
        AgentDelegateTarget(agent_type=" ")
    with pytest.raises(AgentDefinitionError):
        AgentDelegateTarget(agent_type="ResearchAgent", agent_name=" ")
    with pytest.raises(AgentDefinitionError):
        DelegationBudget(max_steps=0)
    with pytest.raises(AgentDefinitionError):
        DelegationBudget(max_tokens=0)
    with pytest.raises(AgentDefinitionError):
        DelegationBudget(timeout_seconds=0)
    with pytest.raises(AgentDefinitionError):
        DelegationPacket(
            id=" ",
            parent_agent_state_id="run-parent",
            target=AgentDelegateTarget(agent_type="ResearchAgent"),
            task={"goal": "inspect"},
        )
    with pytest.raises(AgentDefinitionError):
        DelegationPacket(
            id="delegation-1",
            parent_agent_state_id=" ",
            target=AgentDelegateTarget(agent_type="ResearchAgent"),
            task={"goal": "inspect"},
        )
    with pytest.raises(AgentDefinitionError):
        DelegationResult(
            id=" ",
            packet_id="delegation-1",
            target=AgentDelegateTarget(agent_type="ResearchAgent"),
            summary="done",
        )
    with pytest.raises(AgentDefinitionError):
        DelegationResult(
            id="delegation-result-1",
            packet_id=" ",
            target=AgentDelegateTarget(agent_type="ResearchAgent"),
            summary="done",
        )
    with pytest.raises(AgentDefinitionError):
        DelegationResult(
            id="delegation-result-1",
            packet_id="delegation-1",
            target=AgentDelegateTarget(agent_type="ResearchAgent"),
            summary=" ",
        )


class RecordingDelegate(IAgentDelegate):
    """Test delegate that records the packet and emits one result."""

    def __init__(self) -> None:
        self.last_packet: DelegationPacket | None = None

    async def delegate(
        self,
        packet: DelegationPacket,
    ) -> AsyncGenerator[AgentYield[DelegationResult], None]:
        self.last_packet = packet
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=DelegationResult(
                id="delegation-result-1",
                packet_id=packet.id,
                target=packet.target,
                summary="done",
            ),
        )
