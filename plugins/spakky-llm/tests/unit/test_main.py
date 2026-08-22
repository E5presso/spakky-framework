"""Tests for multi-provider plugin initialization."""

from collections.abc import AsyncIterator
from typing import override

import pytest
from spakky.agent import (
    IAgentModel,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
)
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.llm.config import LlmConfig, LlmProviderApi
from spakky.plugins.llm.error import LlmConfigurationError
from spakky.plugins.llm.main import initialize
from spakky.plugins.llm.model import LlmAgentModel
from spakky.plugins.llm.provider import (
    ILLMProvider,
    LlmModelTarget,
    done_event,
    routing_metadata,
)
from spakky.plugins.llm.providers.anthropic import AnthropicMessagesProvider
from spakky.plugins.llm.providers.google import GoogleGenerateContentProvider
from spakky.plugins.llm.providers.openai import OpenAIChatProvider


class _RecordingOpenAIProvider(ILLMProvider):
    """Undecorated OpenAI-compatible provider base for bootstrap tests."""

    target: LlmModelTarget | None

    def __init__(self) -> None:
        self.target = None

    @property
    @override
    def apis(self) -> frozenset[LlmProviderApi]:
        return frozenset({LlmProviderApi.OPENAI_CHAT_COMPLETIONS})

    @override
    async def complete(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> ModelResponse:
        self.target = target
        return ModelResponse(content="custom", metadata=routing_metadata(target))

    @override
    def stream(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        return self._stream(target)

    async def _stream(
        self,
        target: LlmModelTarget,
    ) -> AsyncIterator[ModelStreamEvent]:
        yield done_event(target, "stop", None)


@Pod()
class _CustomOpenAIProvider(_RecordingOpenAIProvider):
    """User-contributed OpenAI-compatible provider for bootstrap tests."""


@Pod()
class _SecondCustomOpenAIProvider(_RecordingOpenAIProvider):
    """Second user provider used to assert startup ambiguity failure."""


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


async def test_initialize_custom_provider_replaces_first_party_default() -> None:
    """initialize + app.add + app.start resolves one user provider over defaults."""
    app = SpakkyApplication(ApplicationContext())
    initialize(app)
    app.add(_CustomOpenAIProvider)

    app.start()
    response = await app.container.get(IAgentModel).complete(
        ModelRequest(messages=(ModelMessage(ModelMessageRole.USER, "hello"),))
    )
    custom = app.container.get(_CustomOpenAIProvider)

    assert response.content == "custom"
    assert custom.target is not None
    assert custom.target.model_ref == "assistant/default"


def test_initialize_rejects_two_custom_provider_replacements() -> None:
    """initialize + app.add fails instead of choosing among user providers."""
    app = SpakkyApplication(ApplicationContext())
    initialize(app)
    app.add(_CustomOpenAIProvider)
    app.add(_SecondCustomOpenAIProvider)

    with pytest.raises(LlmConfigurationError):
        app.start()
