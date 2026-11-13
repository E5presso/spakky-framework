"""Tests for OAuth plugin initialization."""

from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod

import spakky.plugins.oauth as oauth_api
from spakky.plugins.oauth.client import OAuthClient
from spakky.plugins.oauth.config import OAuthConfig
from spakky.plugins.oauth.error import OAuthClientNotConfiguredError
from spakky.plugins.oauth.main import initialize
from spakky.plugins.oauth.store import (
    InMemoryOAuthAuthorizationStateStore,
    InMemoryOAuthTokenStore,
)

import pytest


@Pod()
class _TokenStore(InMemoryOAuthTokenStore):
    """Application-registered token store."""


@Pod()
class _StateStore(InMemoryOAuthAuthorizationStateStore):
    """Application-registered authorization state store."""


def test_public_api_expect_only_plugin_identity() -> None:
    """The root package exposes the plugin identity, not implementation types."""
    assert oauth_api.PLUGIN_NAME.name == "spakky-oauth"
    assert oauth_api.__all__ == ["PLUGIN_NAME"]


async def test_initialize_with_application_stores_expect_resolved_client() -> None:
    """The plugin wires OAuthClient to the stores the application registers."""
    app = SpakkyApplication(ApplicationContext())
    initialize(app)
    app.add(_TokenStore)
    app.add(_StateStore)

    assert app.container.contains(OAuthConfig)
    assert app.container.contains(OAuthClient)
    app.start()
    client = app.container.get(OAuthClient)

    with pytest.raises(OAuthClientNotConfiguredError):
        await client.access_token("missing", "user-1")
