"""Tests for the vLLM HTTP client boundary."""

from collections.abc import AsyncIterator, Mapping
from json import JSONDecodeError
from typing import Self

import httpx
import pytest

from spakky.plugins.vllm.client import HttpxVllmChatClient
from spakky.plugins.vllm.config import VllmConfig
from spakky.plugins.vllm.error import (
    VllmResponseError,
    VllmTimeoutError,
    VllmTransportError,
)


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


class TimeoutResponse(FakeResponse):
    def raise_for_status(self) -> None:
        """Raise an httpx timeout for timeout mapping."""
        raise httpx.TimeoutException("request timed out")


class FakeAsyncClient:
    response: FakeResponse
    stream_response: "FakeStreamResponse"
    observed_timeout: float | None = None
    observed_url: str | None = None
    observed_json: Mapping[str, object] | None = None
    observed_method: str | None = None

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

    def stream(
        self,
        method: str,
        url: str,
        *,
        json: Mapping[str, object],
    ) -> "FakeStreamContext":
        type(self).observed_method = method
        type(self).observed_url = url
        type(self).observed_json = json
        return FakeStreamContext(type(self).stream_response)


class FakeStreamResponse:
    lines: tuple[str, ...]
    status_error: httpx.HTTPStatusError | None
    stream_error: httpx.TimeoutException | None

    def __init__(
        self,
        lines: tuple[str, ...],
        status_error: httpx.HTTPStatusError | None = None,
        stream_error: httpx.TimeoutException | None = None,
    ) -> None:
        self.lines = lines
        self.status_error = status_error
        self.stream_error = stream_error

    def raise_for_status(self) -> None:
        """Raise the configured streaming status error when present."""
        if self.status_error is not None:
            raise self.status_error

    async def aiter_lines(self) -> AsyncIterator[str]:
        """Yield fake server-sent event lines."""
        if self.stream_error is not None:
            raise self.stream_error
        for line in self.lines:
            yield line


class FakeStreamContext:
    response: FakeStreamResponse

    def __init__(self, response: FakeStreamResponse) -> None:
        self.response = response

    async def __aenter__(self) -> FakeStreamResponse:
        return self.response

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        return None


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


async def test_httpx_client_timeout_expect_timeout_error(monkeypatch) -> None:
    """httpx timeout 실패는 plugin timeout error로 변환된다."""
    FakeAsyncClient.response = TimeoutResponse({})
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(VllmTimeoutError):
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


async def test_httpx_client_stream_decodes_openai_sse_chunks(monkeypatch) -> None:
    """stream()은 OpenAI-compatible SSE data line을 JSON object chunk로 디코딩한다."""
    FakeAsyncClient.stream_response = FakeStreamResponse(
        (
            ": keep-alive",
            "",
            'data: {"choices":[{"delta":{"content":"hi"}}]}',
            "data: [DONE]",
        )
    )
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    chunks = [
        chunk
        async for chunk in HttpxVllmChatClient().stream({"stream": True}, VllmConfig())
    ]

    assert chunks == [{"choices": [{"delta": {"content": "hi"}}]}]
    assert FakeAsyncClient.observed_timeout == 300.0
    assert FakeAsyncClient.observed_method == "POST"
    assert FakeAsyncClient.observed_url == "http://127.0.0.1:8000/v1/chat/completions"
    assert FakeAsyncClient.observed_json == {"stream": True}


@pytest.mark.parametrize(
    "line",
    ["event: nope", "data: []", "data: not-json"],
)
async def test_httpx_client_stream_invalid_chunk_expect_response_error(
    monkeypatch,
    line: str,
) -> None:
    """잘못된 SSE line은 invalid provider stream chunk로 실패한다."""
    FakeAsyncClient.stream_response = FakeStreamResponse((line,))
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(VllmResponseError):
        async for _chunk in HttpxVllmChatClient().stream({}, VllmConfig()):
            continue


async def test_httpx_client_stream_status_error_expect_transport_error(
    monkeypatch,
) -> None:
    """streaming HTTP status 실패는 plugin transport error로 변환된다."""
    FakeAsyncClient.stream_response = FakeStreamResponse(
        (),
        httpx.HTTPStatusError(
            "bad status",
            request=httpx.Request("POST", "http://vllm/v1/chat/completions"),
            response=httpx.Response(500),
        ),
    )
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(VllmTransportError):
        async for _chunk in HttpxVllmChatClient().stream({}, VllmConfig()):
            continue


async def test_httpx_client_stream_timeout_expect_timeout_error(monkeypatch) -> None:
    """streaming timeout은 plugin timeout error로 변환된다."""
    FakeAsyncClient.stream_response = FakeStreamResponse(
        (),
        stream_error=httpx.TimeoutException("stream timed out"),
    )
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(VllmTimeoutError):
        async for _chunk in HttpxVllmChatClient().stream({}, VllmConfig()):
            continue
