"""Tests for the in-memory OAuth stores and system clock."""

from datetime import UTC, datetime, timedelta

from pydantic import SecretStr

from spakky.plugins.oauth.store import (
    InMemoryOAuthAuthorizationStateStore,
    InMemoryOAuthTokenStore,
    SystemOAuthClock,
)
from spakky.plugins.oauth.token import (
    OAuthPendingAuthorization,
    OAuthTokenKey,
    OAuthTokenSet,
)

_KEY = OAuthTokenKey(client="example", subject="user-1")


async def test_token_store_expect_tokens_isolated_per_subject() -> None:
    """Tokens are stored per registration and subject and can be removed twice."""
    store = InMemoryOAuthTokenStore()
    tokens = OAuthTokenSet(client_id="my-app", access_token=SecretStr("token"))

    await store.save(_KEY, tokens)

    assert await store.load(_KEY) == tokens
    assert await store.load(OAuthTokenKey(client="example", subject="user-2")) is None
    await store.delete(_KEY)
    await store.delete(_KEY)
    assert await store.load(_KEY) is None


async def test_state_store_expect_single_use_state() -> None:
    """A started authorization can be taken by exactly one callback."""
    store = InMemoryOAuthAuthorizationStateStore()
    pending = OAuthPendingAuthorization(
        key=_KEY,
        client_id="my-app",
        redirect_uri="https://app.example.test/callback",
        code_verifier=SecretStr("verifier"),
        expires_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    await store.save("state-1", pending)

    assert await store.take("state-1") == pending
    assert await store.take("state-1") is None


def test_system_clock_expect_aware_utc_time() -> None:
    """The default clock reports timezone-aware UTC time."""
    now = SystemOAuthClock().now()

    assert now.utcoffset() == timedelta(0)
