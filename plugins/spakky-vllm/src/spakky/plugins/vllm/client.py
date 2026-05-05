"""HTTP client boundary for the vLLM OpenAI-compatible endpoint."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from json import JSONDecodeError
from typing import override

import httpx
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.vllm.config import VllmConfig
from spakky.plugins.vllm.error import VllmResponseError, VllmTransportError

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
        except httpx.HTTPError as e:
            raise VllmTransportError from e
        except JSONDecodeError as e:
            raise VllmResponseError from e

        if not isinstance(decoded, Mapping):
            raise VllmResponseError
        return decoded
