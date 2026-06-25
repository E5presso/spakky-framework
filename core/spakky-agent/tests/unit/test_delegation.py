"""Tests for agent delegation contracts."""

from collections.abc import AsyncGenerator, Mapping
from typing import cast

import pytest

from spakky.agent import (
    Agent,
    AgentDelegateTarget,
    AgentDefinitionError,
    AgentEvidenceKind,
    AgentExecutionSpec,
    AgentTeammate,
    AgentToolDispatcher,
    AgentToolRuntimeContext,
    AgentYield,
    AgentYieldKind,
    DelegationBudget,
    DelegationContextSlice,
    DelegationExpectedOutput,
    DelegationPacket,
    DelegationResult,
    DelegationReturnPolicy,
    DelegationToolResult,
    Evidence,
    IAgentDelegate,
    JsonValue,
    ModelToolCall,
)
from spakky.agent.delegation import _packet_instruction, _task_payload
from spakky.agent.error import AgentToolDispatchError


@Agent(
    spec=AgentExecutionSpec(
        name="remote-parent",
        teammates=(
            AgentTeammate(
                name="remote",
                card_url="https://remote.example/.well-known/agent-card.json",
            ),
        ),
    )
)
class RemoteParentAgent:
    """Parent fixture exposing a remote teammate delegate port."""

    def __init__(self, delegate: IAgentDelegate | None = None) -> None:
        if delegate is not None:
            self._delegate = delegate


class LocalTeammate:
    """Local teammate type used to exercise missing pod resolution."""


@Agent(
    spec=AgentExecutionSpec(
        name="local-parent",
        teammates=(AgentTeammate(name="local", pod=LocalTeammate),),
    )
)
class LocalParentWithoutChild:
    """Parent fixture declaring but not injecting a local teammate."""


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


async def test_delegate_tool_result_expect_collects_terminal_result() -> None:
    """IAgentDelegate 기본 collector가 terminal result를 tool result로 변환한다."""
    packet = DelegationPacket(
        id="delegation-1",
        parent_agent_state_id="run-parent",
        target=AgentDelegateTarget(agent_type="ResearchAgent"),
        task={"goal": "inspect"},
    )
    delegate = RecordingDelegate()

    result = await delegate.delegate_tool_result(packet)

    assert isinstance(result, DelegationToolResult)
    assert result.summary == "done"
    assert result.metadata["packet_id"] == "delegation-1"


async def test_remote_teammate_tool_expect_dispatches_through_delegate_port() -> None:
    """remote teammate synthetic tool이 IAgentDelegate port로 위임된다."""
    delegate = RecordingDelegate()
    dispatcher = AgentToolDispatcher(
        target=RemoteParentAgent(delegate),
        catalog=Agent.get(RemoteParentAgent).tool_catalog,
        runtime_context=AgentToolRuntimeContext(
            state_id="parent-run",
            conversation_id="thread-1",
            call_id="call-1",
            tool_name="teammate.remote.delegate",
        ),
    )

    result = await dispatcher.dispatch(
        ModelToolCall(
            name="teammate.remote.delegate",
            arguments={"instruction": "inspect", "task": {"topic": "a2a"}},
        )
    )

    assert isinstance(result, DelegationToolResult)
    assert result.metadata["packet_id"] == "parent-run:call-1"
    assert delegate.last_packet is not None
    assert delegate.last_packet.parent_agent_state_id == "parent-run"
    assert delegate.last_packet.target.metadata["card_url"] == (
        "https://remote.example/.well-known/agent-card.json"
    )


async def test_remote_teammate_tool_expect_rejects_missing_delegate_port() -> None:
    """remote teammate tool은 delegate port가 없으면 dispatch error를 낸다."""
    dispatcher = AgentToolDispatcher(
        target=RemoteParentAgent(),
        catalog=Agent.get(RemoteParentAgent).tool_catalog,
        runtime_context=AgentToolRuntimeContext(
            state_id="parent-run",
            conversation_id="thread-1",
            call_id="call-1",
            tool_name="teammate.remote.delegate",
        ),
    )

    with pytest.raises(AgentToolDispatchError):
        await dispatcher.dispatch(
            ModelToolCall(
                name="teammate.remote.delegate",
                arguments={"instruction": "inspect"},
            )
        )


async def test_remote_teammate_tool_expect_rejects_blank_instruction() -> None:
    """teammate tool instruction은 공백일 수 없다."""
    dispatcher = AgentToolDispatcher(
        target=RemoteParentAgent(RecordingDelegate()),
        catalog=Agent.get(RemoteParentAgent).tool_catalog,
        runtime_context=AgentToolRuntimeContext(
            state_id="parent-run",
            conversation_id="thread-1",
            call_id="call-1",
            tool_name="teammate.remote.delegate",
        ),
    )

    with pytest.raises(AgentToolDispatchError):
        await dispatcher.dispatch(
            ModelToolCall(
                name="teammate.remote.delegate",
                arguments={"instruction": " "},
            )
        )


async def test_local_teammate_tool_expect_rejects_missing_child_pod() -> None:
    """local teammate tool은 parent에 child pod가 없으면 dispatch error를 낸다."""
    dispatcher = AgentToolDispatcher(
        target=LocalParentWithoutChild(),
        catalog=Agent.get(LocalParentWithoutChild).tool_catalog,
        runtime_context=AgentToolRuntimeContext(
            state_id="parent-run",
            conversation_id="thread-1",
            call_id="call-1",
            tool_name="teammate.local.delegate",
        ),
    )

    with pytest.raises(AgentToolDispatchError):
        await dispatcher.dispatch(
            ModelToolCall(
                name="teammate.local.delegate",
                arguments={"instruction": "inspect"},
            )
        )


def test_delegation_tool_result_expect_rejects_blank_summary() -> None:
    """DelegationToolResult summary는 model-facing 결과라 공백일 수 없다."""
    with pytest.raises(AgentDefinitionError):
        DelegationToolResult(summary=" ")


async def test_delegate_tool_result_expect_rejects_delegate_without_result() -> None:
    """delegate가 DelegationResult를 내지 않으면 custom dispatch error다."""
    packet = DelegationPacket(
        id="delegation-1",
        parent_agent_state_id="run-parent",
        target=AgentDelegateTarget(agent_type="ResearchAgent"),
        task={"goal": "inspect"},
    )

    with pytest.raises(AgentToolDispatchError):
        await EmptyDelegate().delegate_tool_result(packet)


async def test_delegate_tool_result_expect_ignores_non_result_payloads() -> None:
    """delegate stream의 non-result payload는 terminal result로 보지 않는다."""
    packet = DelegationPacket(
        id="delegation-1",
        parent_agent_state_id="run-parent",
        target=AgentDelegateTarget(agent_type="ResearchAgent"),
        task={"goal": "inspect"},
    )

    with pytest.raises(AgentToolDispatchError):
        await NonResultDelegate().delegate_tool_result(packet)


def test_delegation_helpers_expect_reject_malformed_task_payloads() -> None:
    """defensive helper가 비문자 task key와 instruction 없는 packet을 거부한다."""
    malformed = cast(Mapping[str, JsonValue], {1: "bad"})
    packet = DelegationPacket(
        id="delegation-1",
        parent_agent_state_id="run-parent",
        target=AgentDelegateTarget(agent_type="ResearchAgent"),
        task={},
    )

    with pytest.raises(AgentToolDispatchError):
        _task_payload("inspect", malformed)
    with pytest.raises(AgentToolDispatchError):
        _packet_instruction(packet)


def test_teammate_descriptor_expect_rejects_name_without_schema_token() -> None:
    """teammate 이름이 schema token을 만들 수 없으면 definition error다."""
    with pytest.raises(AgentDefinitionError):

        @Agent(
            spec=AgentExecutionSpec(
                name="bad",
                teammates=(AgentTeammate(name="!!!", pod=LocalTeammate),),
            )
        )
        class BadSchemaAgent:
            """Agent whose teammate name cannot become a schema token."""


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


class EmptyDelegate(IAgentDelegate):
    """Delegate fixture that emits no terminal DelegationResult."""

    async def delegate(
        self,
        packet: DelegationPacket,
    ) -> AsyncGenerator[AgentYield[DelegationResult], None]:
        if False:
            yield AgentYield(
                kind=AgentYieldKind.FINAL,
                payload=DelegationResult(
                    id="never",
                    packet_id=packet.id,
                    target=packet.target,
                    summary="never",
                ),
            )


class NonResultDelegate(IAgentDelegate):
    """Delegate fixture that emits a non-DelegationResult payload."""

    async def delegate(
        self,
        packet: DelegationPacket,
    ) -> AsyncGenerator[AgentYield[DelegationResult], None]:
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=cast(DelegationResult, "not a delegation result"),
        )
