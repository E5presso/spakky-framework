"""Storage and clock ports for the OAuth 2.0 client, with in-memory defaults."""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import override

from spakky.plugins.oauth.token import (
    OAuthPendingAuthorization,
    OAuthState,
    OAuthTokenKey,
    OAuthTokenSet,
)


class IOAuthTokenStore(ABC):
    """Persist the token set each subject holds for each registration."""

    @abstractmethod
    async def load(self, key: OAuthTokenKey) -> OAuthTokenSet | None:
        """Return the stored tokens, or None when the subject never signed in."""
        ...

    @abstractmethod
    async def save(self, key: OAuthTokenKey, tokens: OAuthTokenSet) -> None:
        """Replace the stored tokens for the subject."""
        ...

    @abstractmethod
    async def delete(self, key: OAuthTokenKey) -> None:
        """Remove the stored tokens; removing absent tokens is not an error."""
        ...


class IOAuthAuthorizationStateStore(ABC):
    """Hold started authorizations until their one callback arrives."""

    @abstractmethod
    async def save(self, state: OAuthState, pending: OAuthPendingAuthorization) -> None:
        """Remember one started authorization under its state value."""
        ...

    @abstractmethod
    async def take(self, state: OAuthState) -> OAuthPendingAuthorization | None:
        """Remove and return the authorization, or None when it is unknown or used."""
        ...


class IOAuthClock(ABC):
    """Replaceable wall clock for deterministic expiry decisions."""

    @abstractmethod
    def now(self) -> datetime:
        """Return the current timezone-aware UTC time."""
        ...


class SystemOAuthClock(IOAuthClock):
    """Default clock backed by the system UTC time."""

    @override
    def now(self) -> datetime:
        return datetime.now(UTC)


class InMemoryOAuthTokenStore(IOAuthTokenStore):
    """Process-local token store for development and tests; tokens die on restart."""

    __tokens: dict[OAuthTokenKey, OAuthTokenSet]

    def __init__(self) -> None:
        self.__tokens = {}

    @override
    async def load(self, key: OAuthTokenKey) -> OAuthTokenSet | None:
        return self.__tokens.get(key)

    @override
    async def save(self, key: OAuthTokenKey, tokens: OAuthTokenSet) -> None:
        self.__tokens[key] = tokens

    @override
    async def delete(self, key: OAuthTokenKey) -> None:
        self.__tokens.pop(key, None)


class InMemoryOAuthAuthorizationStateStore(IOAuthAuthorizationStateStore):
    """Process-local state store; callbacks must reach the process that started them.

    Authorizations whose ``expires_at`` has passed are dropped on every
    ``save`` and ``take``, so sign-ins abandoned before their callback do not
    accumulate for the life of the process.
    """

    __pending: dict[OAuthState, OAuthPendingAuthorization]
    __clock: IOAuthClock

    def __init__(self, clock: IOAuthClock | None = None) -> None:
        self.__pending = {}
        self.__clock = clock if clock is not None else SystemOAuthClock()

    @override
    async def save(self, state: OAuthState, pending: OAuthPendingAuthorization) -> None:
        self._purge_expired()
        self.__pending[state] = pending

    @override
    async def take(self, state: OAuthState) -> OAuthPendingAuthorization | None:
        self._purge_expired()
        return self.__pending.pop(state, None)

    def _purge_expired(self) -> None:
        now = self.__clock.now()
        expired = [
            state
            for state, pending in self.__pending.items()
            if pending.expires_at <= now
        ]
        for state in expired:
            del self.__pending[state]
