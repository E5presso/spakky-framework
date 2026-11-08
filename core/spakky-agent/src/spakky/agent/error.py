"""Error classes for the spakky-agent package."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyAgentError(AbstractSpakkyFrameworkError, ABC):
    """Base class for agent-related errors."""

    ...


class AgentDefinitionError(AbstractSpakkyAgentError):
    """Raised when an agent contract cannot be defined safely."""

    message = "Agent definition is invalid"


class AgentToolBindingError(AbstractSpakkyAgentError):
    """Raised when a model tool-call payload cannot be bound safely."""

    message = "Agent tool invocation payload is invalid"


class AgentToolDispatchError(AbstractSpakkyAgentError):
    """Raised when a model tool call names a tool absent from the catalog."""

    message = "Agent tool call cannot be dispatched"


class AgentEvidenceOriginQueryUnsupportedError(AbstractSpakkyAgentError):
    """Raised when an evidence store has no index of context origin references."""

    message = "Agent evidence store cannot query context origin references"


class AgentBootstrapError(AbstractSpakkyAgentError):
    """Raised when agent bootstrap validation fails."""

    message = "Agent bootstrap validation failed"


class AgentPersistenceConfigurationError(AgentBootstrapError):
    """Raised when production agent persistence is required but not provided."""

    message = "Agent persistence contribution is required"


class AgentModelConfigurationError(AgentBootstrapError):
    """Raised when an agent requires a model adapter but none is registered."""

    message = "Agent model adapter is required"


class AgentOutputGuardError(AbstractSpakkyAgentError):
    """Raised when an output guard detects unsafe streaming exposure."""

    message = "Agent output guard failed"


class AgentRetrievalError(AbstractSpakkyAgentError):
    """Raised when retrieval results cannot safely enter an agent run."""

    message = "Agent retrieval failed"


class AgentMemoryError(AbstractSpakkyAgentError):
    """Raised when long-term memory cannot safely cross its scoped boundary."""

    message = "Agent memory operation failed"


class AgentSignalMailboxConfigurationError(AgentBootstrapError):
    """Raised when a run must wait for live input but has no signal mailbox."""

    message = "Agent signal mailbox is required to wait for live input"


class AgentSignalInboxConflictError(AbstractSpakkyAgentError):
    """Raised when one runner opens two live inboxes for the same agent state."""

    message = "Agent state already has an open signal inbox on this runner"
