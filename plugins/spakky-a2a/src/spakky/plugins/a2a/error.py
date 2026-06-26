"""A2A plugin error hierarchy.

Provides the base error class plus concrete errors raised while deriving an
AgentCard, projecting neutral agent events onto A2A task events, and resolving a
registered A2A agent server.
"""

from abc import ABC
from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyA2AError(AbstractSpakkyFrameworkError, ABC):
    """Base exception for all Spakky A2A plugin errors."""

    ...


class A2AAgentServerNotRegisteredError(AbstractSpakkyA2AError):
    """Raised when no A2A agent server is registered for a requested name."""

    message = "No A2A agent server is registered for the agent name"

    def __init__(self, agent_name: str) -> None:
        super().__init__()
        self.agent_name = agent_name


class A2AAgentCardDerivationError(AbstractSpakkyA2AError):
    """Raised when an AgentCard cannot be derived from an @Agent declaration."""

    message = "Cannot derive an AgentCard from the agent declaration"

    def __init__(self, agent_name: str) -> None:
        super().__init__()
        self.agent_name = agent_name


class A2AEndpointConflictError(AbstractSpakkyA2AError):
    """Raised when multiple A2A agents claim the same ASGI mount path."""

    message = "A2A endpoint path is claimed by more than one exposed agent"


class UnsupportedAgentEventError(AbstractSpakkyA2AError):
    """Raised when an AgentEvent kind has no A2A task-event projection."""

    message = "Agent event kind cannot be projected to an A2A event"

    def __init__(self, kind: str) -> None:
        super().__init__()
        self.kind = kind


class UnsupportedFinalOutputError(AbstractSpakkyA2AError):
    """Raised when a final agent output cannot be projected to an A2A part."""

    message = "Agent final output cannot be projected to an A2A part"

    def __init__(self, output_type: type[object]) -> None:
        super().__init__()
        self.output_type = output_type


class InvalidApprovalDecisionError(AbstractSpakkyA2AError):
    """Raised when an inbound approval-decision part carries an unknown decision."""

    message = "Inbound approval decision is not a known ApprovalDecision"

    def __init__(self, decision: str) -> None:
        super().__init__()
        self.decision = decision


class A2ARunResolutionError(AbstractSpakkyA2AError):
    """Raised when an inbound A2A request carries invalid run configuration."""

    message = "A2A run request could not be resolved to a runnable agent run"

    def __init__(self, field: str) -> None:
        super().__init__()
        self.field = field


class UnsupportedA2AGrpcResultError(AbstractSpakkyA2AError):
    """Raised when a unary A2A gRPC method returns an unsupported result."""

    message = "A2A gRPC result type is not supported"

    def __init__(self, result_type: type[object]) -> None:
        super().__init__()
        self.result_type = result_type


class UnsupportedA2AGrpcEventError(AbstractSpakkyA2AError):
    """Raised when a streaming A2A gRPC event cannot be wrapped."""

    message = "A2A gRPC event type is not supported"

    def __init__(self, event_type: type[object]) -> None:
        super().__init__()
        self.event_type = event_type
