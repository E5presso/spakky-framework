"""Tests for multi-provider plugin initialization."""

from spakky.agent import IAgentModel
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

from spakky.plugins.llm.config import LlmConfig
from spakky.plugins.llm.main import initialize
from spakky.plugins.llm.model import LlmAgentModel
from spakky.plugins.llm.providers.anthropic import AnthropicMessagesProvider
from spakky.plugins.llm.providers.google import GoogleGenerateContentProvider
from spakky.plugins.llm.providers.openai import OpenAIChatProvider


def test_initialize_registers_router_and_all_native_sdk_adapters() -> None:
    """entry point는 단일 IAgentModel router와 세 native API adapter를 등록한다."""
    app = SpakkyApplication(ApplicationContext())

    initialize(app)

    assert app.container.contains(LlmConfig)
    assert app.container.contains(OpenAIChatProvider)
    assert app.container.contains(AnthropicMessagesProvider)
    assert app.container.contains(GoogleGenerateContentProvider)
    assert app.container.contains(LlmAgentModel)
    app.start()
    assert isinstance(app.container.get(IAgentModel), LlmAgentModel)
