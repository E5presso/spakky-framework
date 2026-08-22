"""CI-safe acceptance coverage for the spakky-llm plugin boundary."""

from types import TracebackType
from unittest.mock import MagicMock, patch

from openai.types.chat import ChatCompletion
from spakky.agent import (
    IAgentModel,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
)
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

from spakky.plugins.llm.main import initialize
from spakky.plugins.llm.providers import openai as openai_provider


class _FakeCompletions:
    """Record the SDK call while returning a typed official response model."""

    def __init__(self) -> None:
        self.request: dict[str, object] | None = None

    async def create(self, **request: object) -> ChatCompletion:
        self.request = request
        return ChatCompletion.model_validate(
            {
                "id": "chatcmpl-acceptance",
                "object": "chat.completion",
                "created": 1,
                "model": "served-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "official SDK boundary",
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 2,
                    "total_tokens": 5,
                },
            }
        )


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class _FakeAsyncOpenAI:
    """Minimal async lifecycle used by the official SDK adapter."""

    def __init__(self, completions: _FakeCompletions) -> None:
        self.chat = _FakeChat(completions)

    async def __aenter__(self) -> "_FakeAsyncOpenAI":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


async def test_plugin_acceptance_routes_default_vllm_through_openai_sdk() -> None:
    """Plugin bootstrap부터 router와 공식 SDK mapping까지 한 경로로 동작한다."""
    app = SpakkyApplication(ApplicationContext())
    initialize(app)
    app.start()
    completions = _FakeCompletions()
    sdk = _FakeAsyncOpenAI(completions)
    constructor = MagicMock(return_value=sdk)

    with patch.object(openai_provider, "AsyncOpenAI", constructor):
        response = await app.container.get(IAgentModel).complete(
            ModelRequest(
                messages=(ModelMessage(ModelMessageRole.USER, "hello"),),
            )
        )

    assert response.content == "official SDK boundary"
    assert response.usage.total_tokens == 5
    assert response.metadata["provider"] == "vllm"
    assert completions.request is not None
    assert completions.request["model"] == "default"
    constructor.assert_called_once_with(
        api_key="EMPTY",
        admin_api_key="",
        base_url="http://127.0.0.1:8000/v1",
        organization="",
        project="",
        webhook_secret="",
        timeout=30.0,
        max_retries=0,
        default_headers={},
    )
