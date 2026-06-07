"""Auth boundary helpers for RabbitMQ consumer callbacks."""

from collections.abc import Mapping
from contextvars import ContextVar, Token

from spakky.auth import (
    AUTH_CONTEXT_SNAPSHOT_HEADER_KEY,
    AUTH_CONTEXT_SNAPSHOT_METADATA_KEY,
    EXPIRED_SNAPSHOT_DECISION,
    INVALID_SNAPSHOT_DECISION,
    MISSING_SNAPSHOT_DECISION,
    VERIFICATION_PROVIDER_UNAVAILABLE_DECISION,
    AuthInvocation,
    AuthInvocationAttribute,
    AuthRequirementDeniedError,
    AuthVerificationProviderUnavailableError,
    ExpiredAuthContextSnapshotError,
    IAuthContextSnapshotVerifier,
    InvalidAuthContextSnapshotError,
    MissingAuthContextSnapshotError,
    store_auth_context,
)
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.domain.models.event import AbstractEvent

RABBITMQ_AUTH_BOUNDARY = "rabbitmq"
"""AuthInvocation boundary value used for RabbitMQ consumer handlers."""

RABBITMQ_EVENT_NAME_ATTRIBUTE = "event_name"
"""AuthInvocation attribute carrying the integration event name."""

RABBITMQ_SNAPSHOT_ATTRIBUTE = "auth_context_snapshot"
"""AuthInvocation attribute carrying the signed snapshot envelope."""

_current_message_headers: ContextVar[Mapping[str, str] | None] = ContextVar(
    "spakky_rabbitmq_message_headers",
    default=None,
)


def set_current_rabbitmq_message_headers(
    headers: Mapping[str, str],
) -> Token[Mapping[str, str] | None]:
    """Set the message headers visible to the post-processor endpoint."""
    return _current_message_headers.set(headers)


def reset_current_rabbitmq_message_headers(
    token: Token[Mapping[str, str] | None],
) -> None:
    """Restore the previous message header context."""
    _current_message_headers.reset(token)


def current_rabbitmq_message_headers() -> Mapping[str, str]:
    """Return the active RabbitMQ message headers for this handler invocation."""
    headers = _current_message_headers.get()
    if headers is None:
        return {}
    return headers


class RabbitMQAuthBoundary:
    """Verify signed snapshots and seed AuthContext for RabbitMQ handlers."""

    _snapshot_verifier: IAuthContextSnapshotVerifier | None
    _application_context: IApplicationContext

    def __init__(
        self,
        application_context: IApplicationContext,
        snapshot_verifier: IAuthContextSnapshotVerifier | None,
    ) -> None:
        self._application_context = application_context
        self._snapshot_verifier = snapshot_verifier

    def seed_auth_context(
        self,
        *,
        event_type: type[AbstractEvent],
        operation: str,
        protected: bool,
    ) -> None:
        """Verify the current message snapshot and seed AuthContext when needed."""
        headers = current_rabbitmq_message_headers()
        snapshot_envelope = self._snapshot_envelope(headers)
        if snapshot_envelope is None:
            if protected:
                raise AuthRequirementDeniedError(MISSING_SNAPSHOT_DECISION)
            return
        verifier = self._snapshot_verifier
        if verifier is None:
            raise AuthRequirementDeniedError(VERIFICATION_PROVIDER_UNAVAILABLE_DECISION)
        try:
            auth_context = verifier.verify_snapshot(
                snapshot_envelope,
                self._invocation(event_type, operation, snapshot_envelope),
            )
        except MissingAuthContextSnapshotError as error:
            raise AuthRequirementDeniedError(MISSING_SNAPSHOT_DECISION) from error
        except InvalidAuthContextSnapshotError as error:
            raise AuthRequirementDeniedError(INVALID_SNAPSHOT_DECISION) from error
        except ExpiredAuthContextSnapshotError as error:
            raise AuthRequirementDeniedError(EXPIRED_SNAPSHOT_DECISION) from error
        except AuthVerificationProviderUnavailableError as error:
            raise AuthRequirementDeniedError(
                VERIFICATION_PROVIDER_UNAVAILABLE_DECISION
            ) from error
        store_auth_context(self._application_context, auth_context)

    def _snapshot_envelope(self, headers: Mapping[str, str]) -> str | None:
        snapshot = headers.get(AUTH_CONTEXT_SNAPSHOT_METADATA_KEY)
        if snapshot is not None:
            return snapshot
        return headers.get(AUTH_CONTEXT_SNAPSHOT_HEADER_KEY)

    def _invocation(
        self,
        event_type: type[AbstractEvent],
        operation: str,
        snapshot_envelope: str,
    ) -> AuthInvocation:
        return AuthInvocation(
            boundary=RABBITMQ_AUTH_BOUNDARY,
            operation=operation,
            attributes=(
                AuthInvocationAttribute(
                    name=RABBITMQ_EVENT_NAME_ATTRIBUTE,
                    value=event_type.__name__,
                ),
                AuthInvocationAttribute(
                    name=RABBITMQ_SNAPSHOT_ATTRIBUTE,
                    value=snapshot_envelope,
                ),
            ),
        )
