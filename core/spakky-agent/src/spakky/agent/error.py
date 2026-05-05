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


class AgentBootstrapError(AbstractSpakkyAgentError):
    """Raised when agent bootstrap validation fails."""

    message = "Agent bootstrap validation failed"


class AgentPersistenceConfigurationError(AgentBootstrapError):
    """Raised when production agent persistence is required but not provided."""

    message = "Agent persistence contribution is required"


class AgentModelConfigurationError(AgentBootstrapError):
    """Raised when an agent requires a model adapter but none is registered."""

    message = "Agent model adapter is required"
