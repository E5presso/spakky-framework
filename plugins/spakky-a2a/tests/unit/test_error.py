"""Tests for the A2A plugin error hierarchy."""

from spakky.core.common.error import AbstractSpakkyFrameworkError

from spakky.plugins.a2a.error import (
    AbstractSpakkyA2AError,
    A2AAgentCardDerivationError,
    A2AAgentServerNotRegisteredError,
    A2ARunResolutionError,
    InvalidApprovalDecisionError,
    UnsupportedAgentEventError,
    UnsupportedFinalOutputError,
)


def test_a2a_errors_inherit_framework_base() -> None:
    """Every A2A error inherits the framework error base for uniform handling."""
    assert issubclass(AbstractSpakkyA2AError, AbstractSpakkyFrameworkError)


def test_not_registered_error_carries_agent_name() -> None:
    """A2AAgentServerNotRegisteredError preserves the missing agent name."""
    error = A2AAgentServerNotRegisteredError("planner")

    assert error.agent_name == "planner"
    assert error.message == "No A2A agent server is registered for the agent name"


def test_card_derivation_error_carries_agent_name() -> None:
    """A2AAgentCardDerivationError preserves the offending agent name."""
    error = A2AAgentCardDerivationError("planner")

    assert error.agent_name == "planner"


def test_unsupported_event_error_carries_kind() -> None:
    """UnsupportedAgentEventError preserves the unprojectable event kind."""
    error = UnsupportedAgentEventError("mystery")

    assert error.kind == "mystery"


def test_unsupported_final_output_error_carries_type() -> None:
    """UnsupportedFinalOutputError preserves the offending output type."""
    error = UnsupportedFinalOutputError(int)

    assert error.output_type is int


def test_invalid_approval_decision_error_carries_decision() -> None:
    """InvalidApprovalDecisionError preserves the unknown decision string."""
    error = InvalidApprovalDecisionError("maybe")

    assert error.decision == "maybe"


def test_a2a_run_resolution_error_preserves_field() -> None:
    """A2ARunResolutionError preserves the invalid inbound field."""
    error = A2ARunResolutionError("modelSelection")

    assert error.field == "modelSelection"
    assert (
        error.message == "A2A run request could not be resolved to a runnable agent run"
    )
