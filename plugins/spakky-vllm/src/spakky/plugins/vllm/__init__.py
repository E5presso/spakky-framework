"""vLLM model adapter plugin for Spakky Agent."""

from spakky.core.application.plugin import Plugin

from spakky.plugins.vllm.client import HttpxVllmChatClient, IVllmChatClient
from spakky.plugins.vllm.config import VllmConfig
from spakky.plugins.vllm.error import (
    AbstractVllmError,
    VllmModelRefusalError,
    VllmResponseError,
    VllmStreamingDisabledError,
    VllmStreamingNotImplementedError,
    VllmTimeoutError,
    VllmTransportError,
)
from spakky.plugins.vllm.model import VllmAgentModel

PLUGIN_NAME = Plugin(name="spakky-vllm")
"""Plugin identifier for the vLLM adapter package."""

__all__ = [
    "AbstractVllmError",
    "HttpxVllmChatClient",
    "IVllmChatClient",
    "PLUGIN_NAME",
    "VllmAgentModel",
    "VllmConfig",
    "VllmModelRefusalError",
    "VllmResponseError",
    "VllmStreamingDisabledError",
    "VllmStreamingNotImplementedError",
    "VllmTimeoutError",
    "VllmTransportError",
]
