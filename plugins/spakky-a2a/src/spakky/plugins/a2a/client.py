"""Official a2a-sdk client wrapper for remote teammate calls."""

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from uuid import uuid4
from urllib.parse import urlsplit

import httpx
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.types import (
    AgentCard,
    GetTaskRequest,
    Message,
    Part,
    Role,
    SendMessageConfiguration,
    SendMessageRequest,
    StreamResponse,
    Task,
)

DEFAULT_AGENT_CARD_PATH = "/.well-known/agent-card.json"
"""Default A2A well-known AgentCard route."""


@dataclass(frozen=True, slots=True)
class RemoteA2AMessage:
    """Message envelope sent to a remote A2A teammate."""

    text: str
    task_id: str | None = None
    context_id: str | None = None
    message_id: str = field(default_factory=lambda: f"message-{uuid4()}")


class A2ARemoteAgentClient:
    """Small wrapper around the official a2a-sdk client and types."""

    _httpx_client: httpx.AsyncClient | None
    _config: ClientConfig
    _factory: ClientFactory

    def __init__(
        self,
        *,
        httpx_client: httpx.AsyncClient | None = None,
        config: ClientConfig | None = None,
    ) -> None:
        self._httpx_client = httpx_client
        self._config = config or ClientConfig(httpx_client=httpx_client)
        self._factory = ClientFactory(self._config)

    async def resolve_card(self, card_url: str) -> AgentCard:
        """Fetch a remote AgentCard with the SDK resolver."""
        parts = urlsplit(card_url)
        base_url = f"{parts.scheme}://{parts.netloc}"
        path = parts.path or DEFAULT_AGENT_CARD_PATH
        async with self._http_client() as client:
            resolver = A2ACardResolver(client, base_url=base_url)
            return await resolver.get_agent_card(path)

    async def send_message(
        self,
        card_url: str,
        message: RemoteA2AMessage,
    ) -> tuple[StreamResponse, ...]:
        """Send a message and collect the SDK response stream."""
        return tuple([event async for event in self.stream_message(card_url, message)])

    async def stream_message(
        self,
        card_url: str,
        message: RemoteA2AMessage,
    ) -> AsyncGenerator[StreamResponse, None]:
        """Send a message and yield remote task/message updates as they arrive."""
        card = await self.resolve_card(card_url)
        client = self._factory.create(card)
        request = SendMessageRequest(
            message=Message(
                role=Role.ROLE_USER,
                message_id=message.message_id,
                task_id=message.task_id or "",
                context_id=message.context_id or "",
                parts=[Part(text=message.text)],
            ),
            configuration=SendMessageConfiguration(return_immediately=False),
        )
        try:
            async for event in client.send_message(request):
                yield event
        finally:
            await client.close()

    async def get_task(self, card_url: str, task_id: str) -> Task:
        """Fetch a remote A2A task by id using the SDK client."""
        card = await self.resolve_card(card_url)
        client = self._factory.create(card)
        try:
            return await client.get_task(GetTaskRequest(id=task_id))
        finally:
            await client.close()

    def _http_client(self) -> AbstractAsyncContextManager[httpx.AsyncClient]:
        if self._httpx_client is not None:
            return _BorrowedAsyncClient(self._httpx_client)
        return httpx.AsyncClient()


class _BorrowedAsyncClient:
    """Async context manager that leaves caller-owned httpx clients open."""

    _client: httpx.AsyncClient

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None
