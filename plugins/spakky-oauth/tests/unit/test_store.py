"""Tests for the in-memory OAuth stores and system clock."""

from datetime import UTC, datetime, timedelta
from typing import override

from pydantic import SecretStr

from spakky.plugins.oauth.store import (
    IOAuthClock,
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
_NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)


class _Clock(IOAuthClock):
    def __init__(self) -> None:
        self.current = _NOW

    @override
    def now(self) -> datetime:
        return self.current


def _pending(expires_at: datetime) -> OAuthPendingAuthorization:
    return OAuthPendingAuthorization(
        key=_KEY,
        client_id="my-app",
        redirect_uri="https://app.example.test/callback",
        code_verifier=SecretStr("verifier"),
        expires_at=expires_at,
    )


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
    store = InMemoryOAuthAuthorizationStateStore(_Clock())
    pending = _pending(_NOW + timedelta(minutes=10))

    await store.save("state-1", pending)

    assert await store.take("state-1") == pending
    assert await store.take("state-1") is None


async def test_state_store_after_expiry_expect_state_dropped() -> None:
    """A sign-in abandoned past its expiry is gone, even before any callback."""
    clock = _Clock()
    store = InMemoryOAuthAuthorizationStateStore(clock)
    await store.save("abandoned", _pending(_NOW + timedelta(minutes=10)))

    clock.current = _NOW + timedelta(minutes=10)

    assert await store.take("abandoned") is None


async def test_state_store_save_expect_expired_states_purged() -> None:
    """Saving a new state drops expired ones so abandoned sign-ins do not pile up."""
    clock = _Clock()
    store = InMemoryOAuthAuthorizationStateStore(clock)
    for index in range(100):
        await store.save(f"abandoned-{index}", _pending(_NOW + timedelta(minutes=1)))
    await store.save("long-lived", _pending(_NOW + timedelta(minutes=30)))

    clock.current = _NOW + timedelta(minutes=5)
    fresh = _pending(_NOW + timedelta(minutes=15))
    await store.save("fresh", fresh)

    clock.current = _NOW
    # Rewinding the clock cannot bring purged states back.
    assert await store.take("abandoned-0") is None
    assert await store.take("abandoned-99") is None
    assert await store.take("fresh") == fresh
    assert await store.take("long-lived") is not None


async def test_state_store_without_clock_expect_system_time_expiry() -> None:
    """Without a clock the store judges expiry against the system UTC time."""
    store = InMemoryOAuthAuthorizationStateStore()
    await store.save("past", _pending(datetime(2000, 1, 1, tzinfo=UTC)))
    future = _pending(datetime(9999, 1, 1, tzinfo=UTC))
    await store.save("future", future)

    assert await store.take("past") is None
    assert await store.take("future") == future


def test_system_clock_expect_aware_utc_time() -> None:
    """The default clock reports timezone-aware UTC time."""
    now = SystemOAuthClock().now()

    assert now.utcoffset() == timedelta(0)
