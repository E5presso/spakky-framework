"""Async, replaceable remote-media URI validation before provider I/O."""

from abc import ABC, abstractmethod
from asyncio import gather, to_thread, wait_for
from ipaddress import IPv4Address, IPv6Address, ip_address
from math import isfinite
from socket import SOCK_STREAM, getaddrinfo
from typing import override
from urllib.parse import urlsplit

from spakky.agent import ModelRequest
from spakky.agent.content import (
    AudioPart,
    DocumentPart,
    ImagePart,
    VideoPart,
    model_content_parts,
)

from spakky.plugins.llm.error import LlmConfigurationError
from spakky.plugins.llm.provider import LlmModelTarget

_MEDIA_TYPES = (ImagePart, AudioPart, VideoPart, DocumentPart)


class ILLMMediaUriPolicy(ABC):
    """Replaceable async authority for provider-bound remote media references."""

    @abstractmethod
    async def validate(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> None:
        """Validate every URI without blocking the caller's event-loop thread."""
        ...


class PublicLlmMediaUriPolicy(ILLMMediaUriPolicy):
    """Resolve untrusted HTTP(S) hostnames off-loop and require public addresses."""

    def __init__(self, timeout_seconds: float = 2.0) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int | float)
            or not isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise LlmConfigurationError
        self.__timeout_seconds = float(timeout_seconds)

    @override
    async def validate(
        self,
        target: LlmModelTarget,
        request: ModelRequest,
    ) -> None:
        _ = target
        endpoints: set[tuple[str, int]] = set()
        for message in request.assemble_messages():
            for part in model_content_parts(message.content):
                if not isinstance(part, _MEDIA_TYPES) or part.uri is None:
                    continue
                parsed = urlsplit(part.uri)
                host = parsed.hostname
                if (
                    host is None
                    or parsed.scheme not in {"http", "https"}
                    or host.endswith(".test")
                    or part.safety_limits.allowed_uri_hosts is not None
                ):
                    continue
                try:
                    ip_address(host)
                except ValueError:
                    endpoints.add((host, parsed.port or 443))
        if endpoints:
            await gather(
                *(self._resolve(host, port) for host, port in sorted(endpoints))
            )

    async def _resolve(self, host: str, port: int) -> None:
        try:
            addresses = await wait_for(
                to_thread(getaddrinfo, host, port, type=SOCK_STREAM),
                timeout=self.__timeout_seconds,
            )
        except (OSError, TimeoutError, ValueError) as error:
            raise LlmConfigurationError(
                details={"reason": "media_uri_resolution_failed"}
            ) from error
        if not addresses:
            raise LlmConfigurationError(
                details={"reason": "media_uri_resolution_failed"}
            )
        for address_info in addresses:
            resolved = address_info[4][0]
            if not isinstance(resolved, str):
                raise LlmConfigurationError(
                    details={"reason": "media_uri_resolution_invalid"}
                )
            try:
                address = ip_address(resolved.split("%", maxsplit=1)[0])
            except ValueError as error:
                raise LlmConfigurationError(
                    details={"reason": "media_uri_resolution_invalid"}
                ) from error
            if not _is_public_address(address):
                raise LlmConfigurationError(
                    details={"reason": "media_uri_address_not_public"}
                )


def _is_public_address(address: IPv4Address | IPv6Address) -> bool:
    if address.is_multicast or not address.is_global:
        return False
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        mapped = address.ipv4_mapped
        return mapped.is_global and not mapped.is_multicast
    return True
