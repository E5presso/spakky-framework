"""Tests for off-loop, replaceable provider-bound media URI validation."""

from asyncio import create_task, sleep as async_sleep
from threading import Event as ThreadEvent
from time import sleep
from typing import cast

import pytest
from pydantic import SecretStr
from spakky.agent import ModelMessage, ModelRequest
from spakky.agent.content import ImagePart, MediaSafetyLimits

from spakky.plugins.llm import media as media_module
from spakky.plugins.llm.config import (
    LlmModelRoute,
    LlmProfile,
    LlmProviderApi,
)
from spakky.plugins.llm.error import LlmConfigurationError
from spakky.plugins.llm.media import PublicLlmMediaUriPolicy
from spakky.plugins.llm.provider import LlmModelTarget


def _target() -> LlmModelTarget:
    profile = LlmProfile(
        provider="openai",
        api=LlmProviderApi.OPENAI_CHAT_COMPLETIONS,
        api_key=SecretStr("secret"),
    )
    return LlmModelTarget(
        model_ref="assistant/default",
        profile_name="openai",
        profile=profile,
        route=LlmModelRoute(profile="openai", model="physical"),
    )


def _request(*parts: ImagePart) -> ModelRequest:
    return ModelRequest(messages=(ModelMessage.user(parts),))


@pytest.mark.parametrize("timeout", [True, 0, float("inf"), cast(float, "bad")])
def test_media_uri_policy_rejects_invalid_timeout(timeout: float) -> None:
    """Resolver timeouts are finite positive operator configuration."""
    with pytest.raises(LlmConfigurationError):
        PublicLlmMediaUriPolicy(timeout)


async def test_media_uri_policy_skips_non_network_or_explicit_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reserved tests, literals, custom schemes, and host allowlists need no DNS."""
    calls: list[str] = []

    def forbidden(host: str, port: int, *, type: int) -> object:
        calls.append(host)
        return ((2, type, 6, "", ("127.0.0.1", port)),)

    monkeypatch.setattr(media_module, "getaddrinfo", forbidden)
    explicit = MediaSafetyLimits(
        allowed_uri_hosts=frozenset({"private.example.invalid"})
    )
    request = _request(
        ImagePart.from_uri(
            "https://assets.example.test/x.png",
            media_type="image/png",
        ),
        ImagePart.from_uri("https://8.8.8.8/x.png", media_type="image/png"),
        ImagePart.from_uri(
            "gs://bucket/x.png",
            media_type="image/png",
            limits=MediaSafetyLimits(allowed_uri_schemes=frozenset({"gs"})),
        ),
        ImagePart.from_uri(
            "https://private.example.invalid/x.png",
            media_type="image/png",
            limits=explicit,
        ),
    )

    await PublicLlmMediaUriPolicy().validate(_target(), request)

    assert calls == []


async def test_media_uri_policy_resolves_unique_hosts_off_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blocking resolver work does not stall a concurrent event-loop heartbeat."""
    started = ThreadEvent()
    calls: list[str] = []

    def blocking(host: str, port: int, *, type: int) -> object:
        calls.append(host)
        started.set()
        sleep(0.05)
        return (
            (2, type, 6, "", ("8.8.8.8", port)),
            (10, type, 6, "", ("::ffff:8.8.8.8", port)),
        )

    monkeypatch.setattr(media_module, "getaddrinfo", blocking)
    request = _request(
        ImagePart.from_uri(
            "https://media.example.invalid/a.png",
            media_type="image/png",
        ),
        ImagePart.from_uri(
            "https://media.example.invalid/b.png",
            media_type="image/png",
        ),
    )
    pending = create_task(PublicLlmMediaUriPolicy().validate(_target(), request))
    while not started.is_set():
        await async_sleep(0)

    heartbeat = 0
    await async_sleep(0)
    heartbeat += 1
    assert not pending.done()
    await pending

    assert heartbeat == 1
    assert calls == ["media.example.invalid"]


@pytest.mark.parametrize(
    "resolved",
    [
        (),
        OSError("dns"),
        ((2, 1, 6, "", (cast(str, 1), 443)),),
        ((2, 1, 6, "", ("bad", 443)),),
        ((2, 1, 6, "", ("127.0.0.1", 443)),),
        ((2, 1, 6, "", ("224.0.0.1", 443)),),
        ((2, 1, 6, "", ("ff02::1", 443)),),
        ((2, 1, 6, "", ("::ffff:127.0.0.1", 443)),),
    ],
)
async def test_media_uri_policy_rejects_invalid_resolution(
    monkeypatch: pytest.MonkeyPatch,
    resolved: object,
) -> None:
    """Resolver failures and every non-public address remain typed."""

    def resolve(host: str, port: int, *, type: int) -> object:
        _ = (host, port, type)
        if isinstance(resolved, OSError):
            raise resolved
        return resolved

    monkeypatch.setattr(media_module, "getaddrinfo", resolve)

    with pytest.raises(LlmConfigurationError):
        await PublicLlmMediaUriPolicy().validate(
            _target(),
            _request(
                ImagePart.from_uri(
                    "https://media.example.invalid/x.png",
                    media_type="image/png",
                )
            ),
        )


async def test_media_uri_policy_timeout_is_typed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slow resolver is bounded without blocking the async caller."""

    def slow(host: str, port: int, *, type: int) -> object:
        _ = host
        sleep(0.05)
        return ((2, type, 6, "", ("8.8.8.8", port)),)

    monkeypatch.setattr(media_module, "getaddrinfo", slow)

    with pytest.raises(LlmConfigurationError):
        await PublicLlmMediaUriPolicy(0.001).validate(
            _target(),
            _request(
                ImagePart.from_uri(
                    "https://media.example.invalid/x.png",
                    media_type="image/png",
                )
            ),
        )
