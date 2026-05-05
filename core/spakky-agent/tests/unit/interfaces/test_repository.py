"""Tests for agent persistence repository interfaces."""

from abc import ABCMeta

from spakky.agent import (
    IAgentEvidenceRepository,
    IAgentSignalRepository,
    IAgentStateRepository,
)


def test_agent_state_repository_expect_exposes_materialized_state_methods() -> None:
    """state repository가 저장, 조회, resume 후보 조회를 노출한다."""
    methods = IAgentStateRepository.__abstractmethods__

    assert methods == {
        "get",
        "get_or_none",
        "save",
        "list_by_status",
        "list_resume_candidates",
    }
    assert isinstance(IAgentStateRepository, ABCMeta)


def test_agent_signal_repository_expect_exposes_queue_methods() -> None:
    """signal repository가 durable inbound queue append/consume을 노출한다."""
    methods = IAgentSignalRepository.__abstractmethods__

    assert methods == {
        "append",
        "list_pending",
        "mark_consumed",
    }
    assert isinstance(IAgentSignalRepository, ABCMeta)


def test_agent_signal_repository_expect_list_pending_documents_queue_order() -> None:
    """list_pending contract가 append/queue order 보존을 문서화한다."""
    doc = IAgentSignalRepository.list_pending.__doc__ or ""

    assert "append/queue order" in doc


def test_agent_evidence_repository_expect_exposes_append_read_only_methods() -> None:
    """evidence repository가 update/delete를 agent-facing interface에 노출하지 않는다."""
    methods = IAgentEvidenceRepository.__abstractmethods__

    assert methods == {
        "append",
        "get",
        "list_by_state",
        "list_by_manifest_ref",
    }
    assert "update" not in methods
    assert "delete" not in methods
