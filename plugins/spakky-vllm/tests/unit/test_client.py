"""Tests for the vLLM HTTP client boundary."""

from collections.abc import Mapping
from json import JSONDecodeError
from typing import Self

import httpx
import pytest

from spakky.plugins.vllm.client import HttpxVllmChatClient
from spakky.plugins.vllm.config import VllmConfig
from spakky.plugins.vllm.error import VllmResponseError, VllmTransportError


class FakeResponse:
    body: object
    json_error: JSONDecodeError | None

    def __init__(
        self,
        body: object,
        json_error: JSONDecodeError | None = None,
    ) -> None:
        self.body = body
        self.json_error = json_error

    def raise_for_status(self) -> None:
        """No-op status hook for successful fake responses."""

    def json(self) -> object:
        """Return the fake JSON body or raise the configured decode error."""
        if self.json_error is not None:
            raise self.json_error
        return self.body


class FailingStatusResponse(FakeResponse):
    def raise_for_status(self) -> None:
        """Raise an httpx error for status-failure mapping."""
        raise httpx.HTTPStatusError(
            "bad status",
            request=httpx.Request("POST", "http://vllm/v1/chat/completions"),
            response=httpx.Response(500),
        )


class FakeAsyncClient:
    response: FakeResponse
    observed_timeout: float | None = None
    observed_url: str | None = None
    observed_json: Mapping[str, object] | None = None

    def __init__(self, *, timeout: float) -> None:
        type(self).observed_timeout = timeout

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        return None

    async def post(
        self,
        url: str,
        *,
        json: Mapping[str, object],
    ) -> FakeResponse:
        type(self).observed_url = url
        type(self).observed_json = json
        return type(self).response


async def test_httpx_client_posts_chat_completion_payload(monkeypatch) -> None:
    """HTTP client가 configured endpoint로 payload를 POST하고 JSON object를 반환한다."""
    FakeAsyncClient.response = FakeResponse({"choices": []})
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    response = await HttpxVllmChatClient().complete({"model": "m"}, VllmConfig())

    assert response == {"choices": []}
    assert FakeAsyncClient.observed_timeout == 30.0
    assert FakeAsyncClient.observed_url == "http://127.0.0.1:8000/v1/chat/completions"
    assert FakeAsyncClient.observed_json == {"model": "m"}


async def test_httpx_client_status_error_expect_transport_error(monkeypatch) -> None:
    """httpx status/transport 실패는 plugin transport error로 변환된다."""
    FakeAsyncClient.response = FailingStatusResponse({})
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(VllmTransportError):
        await HttpxVllmChatClient().complete({}, VllmConfig())


async def test_httpx_client_decode_error_expect_response_error(monkeypatch) -> None:
    """JSON decode 실패는 response shape error로 변환된다."""
    FakeAsyncClient.response = FakeResponse(
        {},
        JSONDecodeError("bad json", "", 0),
    )
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(VllmResponseError):
        await HttpxVllmChatClient().complete({}, VllmConfig())


async def test_httpx_client_non_object_json_expect_response_error(monkeypatch) -> None:
    """JSON body가 object가 아니면 provider response로 수용하지 않는다."""
    FakeAsyncClient.response = FakeResponse([])
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(VllmResponseError):
        await HttpxVllmChatClient().complete({}, VllmConfig())
