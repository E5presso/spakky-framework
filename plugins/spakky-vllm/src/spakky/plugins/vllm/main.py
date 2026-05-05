"""Plugin initialization for the vLLM model adapter."""

from spakky.agent import IAgentModel
from spakky.core.application.application import SpakkyApplication

from spakky.plugins.vllm.client import HttpxVllmChatClient
from spakky.plugins.vllm.config import VllmConfig
from spakky.plugins.vllm.model import VllmAgentModel


def initialize(app: SpakkyApplication) -> None:
    """Register vLLM configuration, HTTP client, and IAgentModel adapter."""
    app.add(VllmConfig)
    app.add(HttpxVllmChatClient)
    app.add(VllmAgentModel)
    app.container.bind_to_type(IAgentModel, VllmAgentModel)
