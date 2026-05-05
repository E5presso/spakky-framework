"""Agentic hexagonal architecture contracts for Spakky Framework."""

from spakky.core.application.plugin import Plugin

from spakky.agent.error import (
    AbstractSpakkyAgentError,
    AgentBootstrapError,
    AgentDefinitionError,
    AgentModelConfigurationError,
    AgentPersistenceConfigurationError,
)
from spakky.agent.evidence import AgentEvidence, AgentEvidenceKind
from spakky.agent.execution import (
    Agent,
    AgentExecutionSpec,
    AgentSignalKind,
    RecoveryStrategy,
    StreamingExposureMode,
)
from spakky.agent.interfaces.repository import (
    IAgentEvidenceRepository,
    IAgentSignalRepository,
    IAgentStateRepository,
)
from spakky.agent.interfaces.model import (
    IAgentModel,
    JsonSchemaConstraint,
    ModelError,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    ModelToolChoice,
    ModelToolSpec,
    ModelUsage,
    SamplingOptions,
    StreamingOptions,
    StructuredOutputSpec,
    ToolCallingSpec,
)
from spakky.agent.signal import AgentSignal, ApprovalDecision
from spakky.agent.state import (
    AgentState,
    AgentStateReason,
    AgentStateTransition,
    AgentStatus,
)
from spakky.agent.types import JsonObject, JsonPrimitive, JsonValue
from spakky.agent.yield_ import (
    AgentYield,
    AgentYieldKind,
    AgentYieldPayload,
    Approval,
    Checkpoint,
    Evidence,
    Final,
    Message,
    TextDelta,
)

PLUGIN_NAME = Plugin(name="spakky-agent")
"""Plugin identifier for the Spakky Agent package."""

__all__ = [
    "IAgentModel",
    "IAgentEvidenceRepository",
    "IAgentSignalRepository",
    "IAgentStateRepository",
    "AbstractSpakkyAgentError",
    "Agent",
    "AgentBootstrapError",
    "AgentDefinitionError",
    "AgentEvidence",
    "AgentEvidenceKind",
    "AgentExecutionSpec",
    "AgentModelConfigurationError",
    "AgentPersistenceConfigurationError",
    "AgentSignal",
    "AgentSignalKind",
    "AgentStateReason",
    "AgentStateTransition",
    "AgentState",
    "AgentStatus",
    "AgentYield",
    "AgentYieldKind",
    "AgentYieldPayload",
    "Approval",
    "ApprovalDecision",
    "Checkpoint",
    "Evidence",
    "Final",
    "JsonObject",
    "JsonPrimitive",
    "JsonSchemaConstraint",
    "JsonValue",
    "Message",
    "ModelError",
    "ModelMessage",
    "ModelMessageRole",
    "ModelRequest",
    "ModelResponse",
    "ModelStreamEvent",
    "ModelStreamEventKind",
    "ModelToolCall",
    "ModelToolChoice",
    "ModelToolSpec",
    "ModelUsage",
    "PLUGIN_NAME",
    "RecoveryStrategy",
    "SamplingOptions",
    "StreamingOptions",
    "StreamingExposureMode",
    "StructuredOutputSpec",
    "TextDelta",
    "ToolCallingSpec",
]
