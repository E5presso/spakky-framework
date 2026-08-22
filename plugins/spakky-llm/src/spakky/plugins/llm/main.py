"""Plugin initialization for the multi-provider LLM adapter."""

from spakky.agent import IAgentModel
from spakky.core.application.application import SpakkyApplication

from spakky.plugins.llm.config import LlmConfig
from spakky.plugins.llm.model import LlmAgentModel
from spakky.plugins.llm.providers.anthropic import AnthropicMessagesProvider
from spakky.plugins.llm.providers.google import GoogleGenerateContentProvider
from spakky.plugins.llm.providers.openai import OpenAIChatProvider


def initialize(app: SpakkyApplication) -> None:
    """Register allowlisted profiles, native SDK adapters, and the model router."""
    app.add(LlmConfig)
    app.add(OpenAIChatProvider)
    app.add(AnthropicMessagesProvider)
    app.add(GoogleGenerateContentProvider)
    app.add(LlmAgentModel)
    app.container.bind_to_type(IAgentModel, LlmAgentModel)
