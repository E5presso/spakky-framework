"""Plugin initialization for cryptography utilities and auth provider."""

from spakky.auth import (
    IAuthContextSnapshotSigner,
    IAuthContextSnapshotVerifier,
    IPasswordHasher,
    IPasswordVerifier,
)
from spakky.core.application.application import SpakkyApplication
from spakky.plugins.cryptography.auth_provider import (
    CryptographyAuthProvider,
    CryptographyAuthProviderConfig,
)


def initialize(app: SpakkyApplication) -> None:
    """Register cryptography config, auth provider, and auth port bindings."""
    app.add(CryptographyAuthProviderConfig)
    app.add(CryptographyAuthProvider)
    app.container.bind_to_type(IAuthContextSnapshotSigner, CryptographyAuthProvider)
    app.container.bind_to_type(IAuthContextSnapshotVerifier, CryptographyAuthProvider)
    app.container.bind_to_type(IPasswordHasher, CryptographyAuthProvider)
    app.container.bind_to_type(IPasswordVerifier, CryptographyAuthProvider)
