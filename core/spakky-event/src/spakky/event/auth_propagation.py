"""Auth snapshot metadata propagation for outbound integration events."""

from typing import override

from spakky.auth import (
    AUTH_CONTEXT_CONTEXT_KEY,
    AUTH_CONTEXT_SNAPSHOT_METADATA_KEY,
    AuthContext,
    AuthSnapshotPropagationConfig,
    IAuthContextSnapshotSigner,
    InvalidAuthContextValueError,
    SnapshotSignRequest,
)
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)

from spakky.event.error import (
    AuthSnapshotPropagationContextUnavailableError,
    AuthSnapshotPropagationSignerUnavailableError,
)

AUTHORIZATION_HEADER = "authorization"
BEARER_AUTHORIZATION_PREFIX = "bearer "


@Pod()
class AuthContextSnapshotHeaderInjector(IApplicationContextAware):
    """Inject signed AuthContextSnapshot metadata into outbound event headers."""

    _auth_snapshot_signer: IAuthContextSnapshotSigner | None
    _auth_snapshot_propagation_config: AuthSnapshotPropagationConfig
    _application_context: IApplicationContext | None

    def __init__(
        self,
        auth_snapshot_signer: IAuthContextSnapshotSigner | None = None,
        auth_snapshot_propagation_config: AuthSnapshotPropagationConfig | None = None,
    ) -> None:
        self._auth_snapshot_signer = auth_snapshot_signer
        self._auth_snapshot_propagation_config = (
            auth_snapshot_propagation_config or AuthSnapshotPropagationConfig()
        )
        self._application_context = None

    @override
    def set_application_context(self, application_context: IApplicationContext) -> None:
        """Inject the application context used to read request-scoped auth state."""
        self._application_context = application_context

    def inject(self, headers: dict[str, str]) -> None:
        """Add signed snapshot metadata when outbound propagation is enabled."""
        self._remove_raw_bearer_headers(headers)
        if not self._auth_snapshot_propagation_config.enabled:
            return
        auth_context = self._current_auth_context()
        if auth_context is None:
            return
        snapshot = self._required_signer().sign_snapshot(
            SnapshotSignRequest(auth_context=auth_context)
        )
        headers[AUTH_CONTEXT_SNAPSHOT_METADATA_KEY] = (
            snapshot.base64url_canonical_json()
        )

    def _current_auth_context(self) -> AuthContext | None:
        application_context = self._application_context
        if application_context is None:
            raise AuthSnapshotPropagationContextUnavailableError()
        value = application_context.get_context_value(AUTH_CONTEXT_CONTEXT_KEY)
        if value is None:
            return None
        if isinstance(value, AuthContext):
            return value
        raise InvalidAuthContextValueError()

    def _required_signer(self) -> IAuthContextSnapshotSigner:
        if self._auth_snapshot_signer is None:
            raise AuthSnapshotPropagationSignerUnavailableError()
        return self._auth_snapshot_signer

    def _remove_raw_bearer_headers(self, headers: dict[str, str]) -> None:
        for key in tuple(headers.keys()):
            if key.lower() == AUTHORIZATION_HEADER and headers[key].lower().startswith(
                BEARER_AUTHORIZATION_PREFIX
            ):
                del headers[key]
