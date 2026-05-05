"""HTTP client boundary for the vLLM OpenAI-compatible endpoint."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Mapping
from json import JSONDecodeError, loads
from typing import override

import httpx
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.vllm.config import VllmConfig
from spakky.plugins.vllm.error import (
    VllmResponseError,
    VllmTimeoutError,
    VllmTransportError,
)

type JsonResponseObject = Mapping[str, object]


class IVllmChatClient(ABC):
    """Boundary used by the model adapter to call vLLM."""

    @abstractmethod
    async def complete(
        self,
        payload: Mapping[str, object],
        config: VllmConfig,
    ) -> JsonResponseObject:
        """Send a non-streaming chat completion request."""
        ...

    @abstractmethod
    def stream(
        self,
        payload: Mapping[str, object],
        config: VllmConfig,
    ) -> AsyncGenerator[JsonResponseObject, None]:
        """Stream OpenAI-compatible chat completion chunks."""
        ...


@Pod()
class HttpxVllmChatClient(IVllmChatClient):
    """httpx-backed client for vLLM's OpenAI-compatible API."""

    @override
    async def complete(
        self,
        payload: Mapping[str, object],
        config: VllmConfig,
    ) -> JsonResponseObject:
        """Send a chat completion request and return the JSON object response."""
        try:
            async with httpx.AsyncClient(
                timeout=config.request_timeout_seconds,
            ) as client:
                response = await client.post(
                    config.chat_completions_url,
                    json=dict(payload),
                )
            response.raise_for_status()
            decoded: object = response.json()
        except httpx.TimeoutException as e:
            raise VllmTimeoutError from e
        except httpx.HTTPError as e:
            raise VllmTransportError from e
        except JSONDecodeError as e:
            raise VllmResponseError from e

        if not isinstance(decoded, Mapping):
            raise VllmResponseError
        return decoded

    @override
    async def stream(
        self,
        payload: Mapping[str, object],
        config: VllmConfig,
    ) -> AsyncGenerator[JsonResponseObject, None]:
        """Stream server-sent event chunks from chat completions."""
        try:
            async with httpx.AsyncClient(
                timeout=config.stream_timeout_seconds,
            ) as client:
                async with client.stream(
                    "POST",
                    config.chat_completions_url,
                    json=dict(payload),
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        chunk = self._decode_sse_line(line)
                        if chunk is not None:
                            yield chunk
        except httpx.TimeoutException as e:
            raise VllmTimeoutError from e
        except httpx.HTTPError as e:
            raise VllmTransportError from e
        except JSONDecodeError as e:
            raise VllmResponseError from e

    def _decode_sse_line(self, line: str) -> JsonResponseObject | None:
        if line == "" or line.startswith(":"):
            return None
        if not line.startswith("data:"):
            raise VllmResponseError
        data = line.removeprefix("data:").strip()
        if data == "[DONE]":
            return None
        decoded: object = loads(data)
        if not isinstance(decoded, Mapping):
            raise VllmResponseError
        return decoded
