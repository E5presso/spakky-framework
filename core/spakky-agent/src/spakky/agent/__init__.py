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
from spakky.agent.interfaces.model import (
    IAgentModel,
    JsonSchemaConstraint,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelUsage,
    SamplingOptions,
    StructuredOutputSpec,
)
from spakky.agent.signal import AgentSignal, ApprovalDecision
from spakky.agent.state import AgentState, AgentStatus
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
    "ModelMessage",
    "ModelMessageRole",
    "ModelRequest",
    "ModelResponse",
    "ModelStreamEvent",
    "ModelStreamEventKind",
    "ModelUsage",
    "PLUGIN_NAME",
    "RecoveryStrategy",
    "SamplingOptions",
    "StreamingExposureMode",
    "StructuredOutputSpec",
    "TextDelta",
]
